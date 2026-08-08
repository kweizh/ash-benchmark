defmodule Outbox.Eventing.Dispatcher do
  @moduledoc """
  The supervised, long-lived process that fans outbox events to subscribers.
  """

  use GenServer
  require Ash.Query

  # API

  def start_link(_opts) do
    GenServer.start_link(__MODULE__, nil, name: __MODULE__)
  end

  def subscribe(subscriber_id, pattern, handler, opts \\ []) do
    GenServer.call(__MODULE__, {:subscribe, subscriber_id, pattern, handler, opts})
  end

  def unsubscribe(subscriber_id) do
    GenServer.call(__MODULE__, {:unsubscribe, subscriber_id})
  end

  def flush do
    GenServer.call(__MODULE__, :flush, :infinity)
  end

  def dead_letters do
    GenServer.call(__MODULE__, :dead_letters)
  end

  def reset do
    # 1. Reset SequenceServer
    Outbox.Eventing.SequenceServer.reset()

    # 2. Delete all stored outbox entries
    events = Outbox.Eventing.Event |> Ash.read!()
    Ash.bulk_destroy!(events, :destroy, %{}, domain: Outbox.Eventing)

    # 3. Reset Dispatcher state
    GenServer.call(__MODULE__, :reset)
  end

  def get_subscribers do
    GenServer.call(__MODULE__, :get_subscribers)
  end

  def get_subscriber(subscriber_id) do
    GenServer.call(__MODULE__, {:get_subscriber, subscriber_id})
  end

  def handle_event(event) do
    subscribers = get_subscribers()
    for {sub_id, sub} <- subscribers do
      if match_topic?(sub.pattern, event.topic) and event.sequence > sub.start_sequence do
        case sub.mode do
          :sync ->
            res =
              try do
                sub.handler.(event)
              rescue
                e ->
                  {:error, {:raised, Exception.message(e)}}
              catch
                kind, value ->
                  {:error, {:raised, "caught #{kind}: #{inspect(value)}"}}
              end

            case res do
              :ok ->
                :ok

              {:error, reason} ->
                GenServer.cast(__MODULE__, {:add_failed_sync_delivery, sub_id, event.sequence, reason})

              other ->
                GenServer.cast(__MODULE__, {:add_failed_sync_delivery, sub_id, event.sequence, other})
            end

          :async ->
            GenServer.cast(__MODULE__, {:add_pending_delivery, sub_id, event.sequence})
        end
      end
    end
    :ok
  end

  # Helper functions

  def resource_to_aggregate_type(resource) do
    resource
    |> Module.split()
    |> List.last()
    |> Macro.underscore()
  end

  def match_topic?(pattern, topic) when is_binary(pattern) and is_binary(topic) do
    pattern_segments = String.split(pattern, ".")
    topic_segments = String.split(topic, ".")
    do_match(pattern_segments, topic_segments)
  end

  defp do_match([], []), do: true
  defp do_match(["#"], _topic_segments), do: true
  defp do_match(["*"], [_]), do: true
  defp do_match(["*" | pat_rest], [_ | top_rest]), do: do_match(pat_rest, top_rest)
  defp do_match([literal | pat_rest], [literal | top_rest]), do: do_match(pat_rest, top_rest)
  defp do_match(_, _), do: false

  # GenServer Callbacks

  @impl true
  def init(_) do
    {:ok, %{
      subscribers: %{},
      subscriber_counter: 0,
      pending_deliveries: [],
      dead_letters: []
    }}
  end

  @impl true
  def handle_call({:subscribe, subscriber_id, pattern, handler, opts}, _from, state) do
    if Map.has_key?(state.subscribers, subscriber_id) do
      {:reply, {:error, :already_subscribed}, state}
    else
      mode = Keyword.get(opts, :mode, :async)
      start_seq = GenServer.call(Outbox.Eventing.SequenceServer, :current_sequence)
      counter = state.subscriber_counter + 1
      sub = %{
        pattern: pattern,
        handler: handler,
        mode: mode,
        registration_order: counter,
        start_sequence: start_seq
      }

      new_subscribers = Map.put(state.subscribers, subscriber_id, sub)
      {:reply, :ok, %{state | subscribers: new_subscribers, subscriber_counter: counter}}
    end
  end

  @impl true
  def handle_call({:unsubscribe, subscriber_id}, _from, state) do
    new_subscribers = Map.delete(state.subscribers, subscriber_id)
    new_pendings = Enum.reject(state.pending_deliveries, & &1.subscriber_id == subscriber_id)

    {:reply, :ok, %{state | subscribers: new_subscribers, pending_deliveries: new_pendings}}
  end

  @impl true
  def handle_call(:flush, _from, state) do
    sorted_pendings =
      state.pending_deliveries
      |> Enum.sort_by(fn delivery ->
        sub = Map.get(state.subscribers, delivery.subscriber_id)
        registration_order = if sub, do: sub.registration_order, else: 0
        {delivery.sequence, registration_order}
      end)

    unique_seqs = sorted_pendings |> Enum.map(& &1.sequence) |> Enum.uniq()

    events_map =
      if unique_seqs == [] do
        %{}
      else
        Outbox.Eventing.Event
        |> Ash.Query.filter(sequence in ^unique_seqs)
        |> Ash.read!()
        |> Map.new(fn event -> {event.sequence, event} end)
      end

    {new_pendings, new_dead_letters} =
      Enum.reduce(sorted_pendings, {[], state.dead_letters}, fn delivery, {acc_pendings, acc_dead} ->
        sub = Map.get(state.subscribers, delivery.subscriber_id)
        event = Map.get(events_map, delivery.sequence)

        cond do
          is_nil(sub) ->
            {acc_pendings, acc_dead}

          is_nil(event) ->
            {[delivery | acc_pendings], acc_dead}

          true ->
            res =
              try do
                sub.handler.(event)
              rescue
                e ->
                  {:error, {:raised, Exception.message(e)}}
              catch
                kind, value ->
                  {:error, {:raised, "caught #{kind}: #{inspect(value)}"}}
              end

            case res do
              :ok ->
                {acc_pendings, acc_dead}

              {:error, reason} ->
                new_attempts = delivery.attempts + 1
                if new_attempts >= 3 do
                  dl = %{
                    subscriber_id: delivery.subscriber_id,
                    sequence: delivery.sequence,
                    attempts: new_attempts,
                    reason: reason,
                    registration_order: sub.registration_order
                  }
                  {acc_pendings, [dl | acc_dead]}
                else
                  updated_delivery = %{delivery | attempts: new_attempts, last_reason: reason}
                  {[updated_delivery | acc_pendings], acc_dead}
                end

              other ->
                new_attempts = delivery.attempts + 1
                if new_attempts >= 3 do
                  dl = %{
                    subscriber_id: delivery.subscriber_id,
                    sequence: delivery.sequence,
                    attempts: new_attempts,
                    reason: other,
                    registration_order: sub.registration_order
                  }
                  {acc_pendings, [dl | acc_dead]}
                else
                  updated_delivery = %{delivery | attempts: new_attempts, last_reason: other}
                  {[updated_delivery | acc_pendings], acc_dead}
                end
            end
        end
      end)

    {:reply, :ok, %{state | pending_deliveries: Enum.reverse(new_pendings), dead_letters: new_dead_letters}}
  end

  @impl true
  def handle_call(:dead_letters, _from, state) do
    sorted_dead_letters =
      state.dead_letters
      |> Enum.sort_by(fn dl ->
        {dl.sequence, dl.registration_order}
      end)
      |> Enum.map(fn dl ->
        %{
          subscriber_id: dl.subscriber_id,
          sequence: dl.sequence,
          attempts: dl.attempts,
          reason: dl.reason
        }
      end)

    {:reply, sorted_dead_letters, state}
  end

  @impl true
  def handle_call(:reset, _from, _state) do
    {:reply, :ok, %{
      subscribers: %{},
      subscriber_counter: 0,
      pending_deliveries: [],
      dead_letters: []
    }}
  end

  @impl true
  def handle_call(:get_subscribers, _from, state) do
    {:reply, state.subscribers, state}
  end

  @impl true
  def handle_call({:get_subscriber, subscriber_id}, _from, state) do
    {:reply, Map.get(state.subscribers, subscriber_id), state}
  end

  @impl true
  def handle_cast({:add_failed_sync_delivery, subscriber_id, sequence, reason}, state) do
    delivery = %{
      subscriber_id: subscriber_id,
      sequence: sequence,
      attempts: 1,
      last_reason: reason
    }
    {:noreply, %{state | pending_deliveries: [delivery | state.pending_deliveries]}}
  end

  @impl true
  def handle_cast({:add_pending_delivery, subscriber_id, sequence}, state) do
    delivery = %{
      subscriber_id: subscriber_id,
      sequence: sequence,
      attempts: 0,
      last_reason: nil
    }
    {:noreply, %{state | pending_deliveries: [delivery | state.pending_deliveries]}}
  end
end
