defmodule Vault.Ledger.Projector do
  @moduledoc """
  Maintains, and can fully rebuild, the `Vault.Ledger.AccountProjection`
  read model by folding the event log.
  """

  require Ash.Query

  alias Vault.Ledger.{AccountProjection, AccountState, Checkpoint, Event, Fold, Hook}

  @checkpoint_name "account_projection"

  @doc "The stored checkpoint sequence, or 0 when absent."
  @spec checkpoint() :: non_neg_integer()
  def checkpoint do
    case checkpoint_row() do
      nil -> 0
      row -> row.sequence
    end
  end

  @doc """
  Applies every event after the stored checkpoint, in ascending `sequence`
  order, updating or creating projection rows and advancing the checkpoint.
  """
  @spec catch_up() :: {:ok, %{applied: non_neg_integer(), checkpoint: non_neg_integer()}}
                       | {:error, {:fold_failed, integer(), term()}}
  def catch_up do
    start_seq = checkpoint()
    events = events_after(start_seq)

    case fold_events(events, start_seq) do
      {:ok, applied, last_seq} ->
        if last_seq != start_seq, do: set_checkpoint(last_seq)
        {:ok, %{applied: applied, checkpoint: last_seq}}

      {:error, error, last_seq} ->
        if last_seq != start_seq, do: set_checkpoint(last_seq)
        {:error, error}
    end
  end

  @doc """
  Discards all projection rows and rebuilds them from the log alone.
  Calls `Vault.Ledger.Hook.run(:after_load)` exactly once, after reading
  the events to fold but before deleting or writing any projection row.
  """
  @spec rebuild_all() :: {:ok, %{rows: non_neg_integer(), checkpoint: non_neg_integer()}}
                          | {:error, {:fold_failed, integer(), term()}}
  def rebuild_all do
    events = all_events()

    Hook.run(:after_load)

    delete_all_projections()

    case fold_events(events, 0) do
      {:ok, _applied, last_seq} ->
        set_checkpoint(last_seq)
        {:ok, %{rows: count_projections(), checkpoint: last_seq}}

      {:error, error, last_seq} ->
        set_checkpoint(last_seq)
        {:error, error}
    end
  end

  @doc """
  The account's state at a point in time: `{:version, n}` folds events with
  `version <= n`, `{:timestamp, datetime}` folds events with
  `recorded_at <= datetime`.
  """
  @spec state_at(String.t(), {:version, non_neg_integer()} | {:timestamp, DateTime.t()}) ::
          {:ok, AccountState.t()} | {:error, term()}
  def state_at(account_id, {:version, n}) when is_integer(n) and n >= 0 do
    events =
      account_id
      |> events_for_account()
      |> Enum.filter(&(&1.version <= n))

    fold_with_sequence_errors(Fold.initial(account_id), events)
  end

  def state_at(account_id, {:timestamp, %DateTime{} = ts}) do
    events =
      account_id
      |> events_for_account()
      |> Enum.filter(&(DateTime.compare(&1.recorded_at, ts) != :gt))

    fold_with_sequence_errors(Fold.initial(account_id), events)
  end

  def state_at(_account_id, _point), do: {:error, :invalid_point}

  @doc "The account's per-event diff list, ascending by `version`."
  @spec audit(String.t()) :: [map()] | {:error, {:fold_failed, integer(), term()}}
  def audit(account_id) do
    events = events_for_account(account_id)
    build_audit(Fold.initial(account_id), events, [])
  end

  # -- internal ---------------------------------------------------------

  defp checkpoint_row do
    Checkpoint
    |> Ash.Query.filter(name == ^@checkpoint_name)
    |> Ash.read_one!(domain: Vault.Ledger, authorize?: false)
  end

  defp set_checkpoint(seq) do
    case checkpoint_row() do
      nil ->
        Checkpoint
        |> Ash.Changeset.for_create(
          :create,
          %{name: @checkpoint_name, sequence: seq},
          domain: Vault.Ledger,
          authorize?: false
        )
        |> Ash.create!()

      row ->
        row
        |> Ash.Changeset.for_update(:update, %{sequence: seq},
          domain: Vault.Ledger,
          authorize?: false
        )
        |> Ash.update!()
    end

    :ok
  end

  defp events_after(seq) do
    Event
    |> Ash.Query.filter(sequence > ^seq)
    |> Ash.Query.sort(sequence: :asc)
    |> Ash.read!(domain: Vault.Ledger, authorize?: false)
  end

  defp all_events do
    Event
    |> Ash.Query.sort(sequence: :asc)
    |> Ash.read!(domain: Vault.Ledger, authorize?: false)
  end

  defp events_for_account(account_id) do
    Event
    |> Ash.Query.filter(account_id == ^account_id)
    |> Ash.Query.sort(sequence: :asc)
    |> Ash.read!(domain: Vault.Ledger, authorize?: false)
  end

  defp fold_events(events, start_seq) do
    Enum.reduce_while(events, {:ok, 0, start_seq}, fn event, {:ok, applied, last_seq} ->
      case apply_to_projection(event) do
        :ok ->
          {:cont, {:ok, applied + 1, event.sequence}}

        {:error, reason} ->
          {:halt, {:error, {:fold_failed, event.sequence, reason}, last_seq}}
      end
    end)
  end

  defp apply_to_projection(event) do
    state = load_projection_state(event.account_id)

    case Fold.apply_event(state, event) do
      {:ok, new_state} ->
        upsert_projection(new_state, event.sequence)
        :ok

      {:error, reason} ->
        {:error, reason}
    end
  end

  defp load_projection_state(account_id) do
    case get_projection(account_id) do
      nil -> Fold.initial(account_id)
      row -> projection_to_state(row)
    end
  end

  defp get_projection(account_id) do
    case Ash.get(AccountProjection, account_id,
           domain: Vault.Ledger,
           authorize?: false,
           not_found_error?: false
         ) do
      {:ok, row} -> row
      {:error, _} -> nil
    end
  end

  defp projection_to_state(row) do
    %AccountState{
      account_id: row.account_id,
      owner: row.owner,
      balance_cents: row.balance_cents,
      status: row.status,
      version: row.version,
      deposit_count: row.deposit_count,
      withdrawal_count: row.withdrawal_count,
      last_event_type: nil,
      last_recorded_at: row.last_recorded_at
    }
  end

  defp upsert_projection(state, sequence) do
    attrs = %{
      account_id: state.account_id,
      owner: state.owner,
      balance_cents: state.balance_cents,
      status: state.status,
      version: state.version,
      deposit_count: state.deposit_count,
      withdrawal_count: state.withdrawal_count,
      last_event_sequence: sequence,
      last_recorded_at: state.last_recorded_at
    }

    case get_projection(state.account_id) do
      nil ->
        AccountProjection
        |> Ash.Changeset.for_create(:create, attrs, domain: Vault.Ledger, authorize?: false)
        |> Ash.create!()

      row ->
        row
        |> Ash.Changeset.for_update(:update, attrs, domain: Vault.Ledger, authorize?: false)
        |> Ash.update!()
    end
  end

  defp delete_all_projections do
    AccountProjection
    |> Ash.read!(domain: Vault.Ledger, authorize?: false)
    |> Enum.each(&Ash.destroy!(&1, domain: Vault.Ledger, authorize?: false))
  end

  defp count_projections do
    AccountProjection
    |> Ash.count!(domain: Vault.Ledger, authorize?: false)
  end

  defp fold_with_sequence_errors(state, events) do
    Enum.reduce_while(events, {:ok, state}, fn event, {:ok, acc} ->
      case Fold.apply_event(acc, event) do
        {:ok, new_state} -> {:cont, {:ok, new_state}}
        {:error, reason} -> {:halt, {:error, {:fold_failed, event.sequence, reason}}}
      end
    end)
  end

  defp build_audit(_state, [], acc), do: Enum.reverse(acc)

  defp build_audit(state, [event | rest], acc) do
    case Fold.apply_event(state, event) do
      {:ok, new_state} ->
        diff = %{
          sequence: event.sequence,
          version: event.version,
          type: event.payload.type,
          balance_before: state.balance_cents,
          balance_after: new_state.balance_cents,
          delta_cents: new_state.balance_cents - state.balance_cents,
          status_before: state.status,
          status_after: new_state.status,
          recorded_at: event.recorded_at
        }

        build_audit(new_state, rest, [diff | acc])

      {:error, reason} ->
        {:error, {:fold_failed, event.sequence, reason}}
    end
  end
end
