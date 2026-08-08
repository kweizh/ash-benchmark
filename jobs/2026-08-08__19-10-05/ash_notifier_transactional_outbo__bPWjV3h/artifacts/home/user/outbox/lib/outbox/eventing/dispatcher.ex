defmodule Outbox.Eventing.Dispatcher do
  @moduledoc """
  A supervised, long-lived process that fans outbox entries out to subscribers.

  Subscribers are registered at runtime with a topic pattern and a handler function.
  Delivery is per `(entry, subscriber)` pair with at-least-once semantics,
  bounded retries (max 3 attempts), and a dead-letter path.
  """

  use GenServer

  # ---- Client API ----

  @doc """
  Subscribes a handler to matching outbox events.

  Options:
    - `:mode` — `:sync` or `:async` (default: `:async`)

  Returns `:ok` or `{:error, :already_subscribed}`.
  """
  def subscribe(subscriber_id, pattern, handler, opts \\ []) do
    GenServer.call(__MODULE__, {:subscribe, subscriber_id, pattern, handler, opts})
  end

  @doc """
  Unsubscribes a previously registered subscriber.
  Always returns `:ok`.
  """
  def unsubscribe(subscriber_id) do
    GenServer.call(__MODULE__, {:unsubscribe, subscriber_id})
  end

  @doc """
  Performs exactly one drain pass: attempts one delivery for each currently-pending
  `(entry, subscriber)` pair, in ascending sequence order, respecting subscriber
  registration order for entries matching multiple subscribers.
  """
  def flush do
    GenServer.call(__MODULE__, :flush)
  end

  @doc """
  Returns all dead-lettered deliveries.
  """
  def dead_letters do
    GenServer.call(__MODULE__, :dead_letters)
  end

  @doc """
  Resets the entire subsystem to pristine state.
  """
  def reset do
    GenServer.call(__MODULE__, :reset)
  end

  @doc """
  Called by the notifier to hand a newly-created event to the dispatcher.
  """
  def dispatch(event) do
    GenServer.cast(__MODULE__, {:dispatch, event})
  end

  # ---- GenServer Callbacks ----

  def start_link(_opts) do
    GenServer.start_link(__MODULE__, [], name: __MODULE__)
  end

  @impl true
  def init(_) do
    Outbox.Eventing.Sequence.init()

    state = %{
      subscribers: %{},
      pending: [],
      dead_letters: []
    }

    {:ok, state}
  end

  @impl true
  def handle_call({:subscribe, id, pattern, handler, opts}, _from, state) do
    if Map.has_key?(state.subscribers, id) do
      {:reply, {:error, :already_subscribed}, state}
    else
      mode = Keyword.get(opts, :mode, :async)

      subscriber = %{
        id: id,
        pattern: pattern,
        handler: handler,
        mode: mode,
        order: map_size(state.subscribers)
      }

      {:reply, :ok, put_in(state.subscribers[id], subscriber)}
    end
  end

  def handle_call({:unsubscribe, id}, _from, state) do
    # Remove subscriber and discard its pending deliveries
    subscribers = Map.delete(state.subscribers, id)
    pending = Enum.reject(state.pending, fn delivery -> delivery.subscriber_id == id end)
    {:reply, :ok, %{state | subscribers: subscribers, pending: pending}}
  end

  def handle_call(:flush, _from, state) do
    # Sort pending by sequence, then by subscriber registration order
    sorted_pending =
      Enum.sort_by(state.pending, fn delivery ->
        {delivery.sequence, delivery.subscriber_order}
      end)

    # Attempt each delivery exactly once
    {remaining, new_dead_letters} =
      Enum.reduce(sorted_pending, {[], state.dead_letters}, fn delivery,
                                                                {acc_pending, acc_dl} ->
        case attempt_delivery(delivery, state.subscribers) do
          :acknowledged ->
            {acc_pending, acc_dl}

          {:failed, reason} ->
            new_attempts = delivery.attempts + 1

            if new_attempts >= 3 do
              # Dead letter
              dl_entry = %{
                subscriber_id: delivery.subscriber_id,
                sequence: delivery.sequence,
                attempts: new_attempts,
                reason: reason
              }

              {acc_pending, [dl_entry | acc_dl]}
            else
              # Retry on next drain
              updated_delivery = %{
                delivery
                | attempts: new_attempts,
                  last_reason: reason
              }

              {[updated_delivery | acc_pending], acc_dl}
            end
        end
      end)

    {:reply, :ok, %{state | pending: remaining, dead_letters: new_dead_letters}}
  end

  def handle_call(:dead_letters, _from, state) do
    # Sort by sequence ascending, then by subscriber registration order
    sorted =
      Enum.sort_by(state.dead_letters, fn dl ->
        sub = Map.get(state.subscribers, dl.subscriber_id)
        sub_order = if sub, do: sub.order, else: 0
        {dl.sequence, sub_order}
      end)

    {:reply, sorted, state}
  end

  def handle_call(:reset, _from, _state) do
    # Reset the sequence counters
    Outbox.Eventing.Sequence.reset()

    # Clear the ETS table for events directly
    table_name = Ash.DataLayer.Ets.Info.table(Outbox.Eventing.Event)
    table_ref = :ets.whereis(table_name)

    if table_ref != :undefined do
      :ets.delete_all_objects(table_ref)
    end

    {:reply, :ok, %{subscribers: %{}, pending: [], dead_letters: []}}
  end

  @impl true
  def handle_cast({:dispatch, event}, state) do
    state = handle_new_event(event, state)
    {:noreply, state}
  end

  # ---- Internal ----

  defp handle_new_event(event, state) do
    state.subscribers
    |> Enum.filter(fn {_id, sub} -> topic_matches?(event.topic, sub.pattern) end)
    |> Enum.reduce(state, fn {_id, sub}, acc_state ->
      case sub.mode do
        :sync ->
          # Sync: deliver immediately in the caller's process
          # (the caller is the notifier, which runs in the writer's process)
          case call_handler(sub.handler, event) do
            :ok ->
              acc_state

            {:error, reason} ->
              # First attempt burned, enqueue for retry
              delivery = %{
                subscriber_id: sub.id,
                sequence: event.sequence,
                attempts: 1,
                subscriber_order: sub.order,
                last_reason: reason
              }

              put_in(acc_state.pending, [delivery | acc_state.pending])
          end

        :async ->
          # Async: just enqueue for later drain
          delivery = %{
            subscriber_id: sub.id,
            sequence: event.sequence,
            attempts: 0,
            subscriber_order: sub.order,
            last_reason: nil
          }

          put_in(acc_state.pending, [delivery | acc_state.pending])
      end
    end)
  end

  defp attempt_delivery(delivery, subscribers) do
    case Map.get(subscribers, delivery.subscriber_id) do
      nil ->
        # Subscriber was removed, acknowledge silently
        :acknowledged

      sub ->
        # We need to look up the event by sequence
        case find_event_by_sequence(delivery.sequence) do
          nil ->
            :acknowledged

          event ->
            case call_handler(sub.handler, event) do
              :ok -> :acknowledged
              {:error, reason} -> {:failed, reason}
            end
        end
    end
  end

  defp call_handler(handler, event) do
    try do
      case handler.(event) do
        :ok -> :ok
        {:error, reason} -> {:error, reason}
        other -> {:error, {:unexpected_return, other}}
      end
    rescue
      e ->
        {:error, {:raised, Exception.message(e)}}
    end
  end

  defp find_event_by_sequence(seq) do
    filter = Ash.Filter.parse!(Outbox.Eventing.Event, %{"sequence" => seq})

    Outbox.Eventing.Event
    |> Ash.Query.new()
    |> Ash.Query.do_filter(filter)
    |> Ash.read(domain: Outbox.Eventing, authorize?: false)
    |> case do
      {:ok, [event | _]} -> event
      _ -> nil
    end
  end

  @doc false
  def topic_matches?(topic, pattern) do
    topic_segments = String.split(topic, ".")
    pattern_segments = String.split(pattern, ".")

    do_match(topic_segments, pattern_segments)
  end

  defp do_match(topic, pattern)

  defp do_match([], []) do
    true
  end

  defp do_match(_topic, ["#"]) do
    # '#' as final segment matches zero or more remaining
    true
  end

  defp do_match([_t | t_rest], ["*" | p_rest]) do
    do_match(t_rest, p_rest)
  end

  defp do_match([t | t_rest], [t | p_rest]) do
    do_match(t_rest, p_rest)
  end

  defp do_match(_, _) do
    false
  end

  # ---- Replay ----

  @doc """
  Replays all events after the given sequence to a specific subscriber.
  Returns `{:ok, delivered_sequences}`.
  """
  def replay(after_seq, subscriber_id) do
    state = :sys.get_state(__MODULE__)

    case Map.get(state.subscribers, subscriber_id) do
      nil ->
        {:ok, []}

      sub ->
        filter = Ash.Filter.parse!(Outbox.Eventing.Event, %{"sequence" => %{"gt" => after_seq}})

        result =
          Outbox.Eventing.Event
          |> Ash.Query.new()
          |> Ash.Query.do_filter(filter)
          |> Ash.read(domain: Outbox.Eventing, authorize?: false)

        case result do
          {:ok, events} ->
            matching =
              events
              |> Enum.filter(fn event -> topic_matches?(event.topic, sub.pattern) end)
              |> Enum.sort_by(& &1.sequence)

            delivered =
              Enum.map(matching, fn event ->
                _ = call_handler(sub.handler, event)
                event.sequence
              end)

            {:ok, delivered}

          _ ->
            {:ok, []}
        end
    end
  end
end
