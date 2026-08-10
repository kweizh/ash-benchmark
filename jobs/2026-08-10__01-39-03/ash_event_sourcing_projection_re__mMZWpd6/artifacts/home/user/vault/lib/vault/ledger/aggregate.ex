defmodule Vault.Ledger.Aggregate do
  @moduledoc """
  Reconstructs an `Vault.Ledger.AccountState` for an account, either by
  folding its whole stream or by accelerating with a verified snapshot.
  """

  require Ash.Query

  alias Vault.Ledger.{Event, Fold, Snapshot, Snapshots}

  @doc "All events for `account_id`, ascending by `version`."
  @spec events_for(String.t()) :: [Event.t()]
  def events_for(account_id) do
    Event
    |> Ash.Query.filter(account_id == ^account_id)
    |> Ash.Query.sort(version: :asc)
    |> Ash.read!(domain: Vault.Ledger, authorize?: false)
  end

  @doc "Folds the account's entire stream from the initial state, ignoring snapshots."
  @spec fold_all(String.t()) :: {:ok, Vault.Ledger.AccountState.t()} | {:error, term()}
  def fold_all(account_id) do
    Fold.replay(Fold.initial(account_id), events_for(account_id))
  end

  @doc """
  Folds the account's state, starting from the highest-version snapshot
  that passes verification (if any), and only folding the events after it.
  """
  @spec current(String.t()) :: {:ok, Vault.Ledger.AccountState.t()} | {:error, term()}
  def current(account_id) do
    case latest_valid_snapshot(account_id) do
      nil ->
        fold_all(account_id)

      %Snapshot{} = snapshot ->
        state = Snapshots.restore(snapshot.state)
        events = Enum.filter(events_for(account_id), &(&1.version > snapshot.version))
        Fold.replay(state, events)
    end
  end

  defp latest_valid_snapshot(account_id) do
    Snapshot
    |> Ash.Query.filter(account_id == ^account_id)
    |> Ash.Query.sort(version: :desc)
    |> Ash.read!(domain: Vault.Ledger, authorize?: false)
    |> Enum.find(&(Snapshots.verify(&1) == :ok))
  end
end
