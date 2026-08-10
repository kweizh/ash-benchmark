defmodule Vault.Ledger.Aggregate do
  alias Vault.Ledger.Fold
  alias Vault.Ledger.Snapshots
  alias Vault.Ledger.Snapshot
  alias Vault.Ledger.Event

  def fold_all(account_id) do
    require Ash.Query
    query = 
      Event
      |> Ash.Query.filter(account_id == ^account_id)
      |> Ash.Query.sort(version: :asc)

    case Ash.read(query) do
      {:ok, events} ->
        initial_state = Fold.initial(account_id)
        Fold.replay(initial_state, events)

      {:error, reason} ->
        {:error, reason}
    end
  end

  def current(account_id) do
    require Ash.Query
    query = 
      Snapshot
      |> Ash.Query.filter(account_id == ^account_id)
      |> Ash.Query.sort(version: :desc)

    case Ash.read(query) do
      {:ok, snapshots} ->
        valid_snapshot = 
          Enum.find(snapshots, fn snapshot ->
            case Snapshots.verify(snapshot) do
              :ok -> true
              _ -> false
            end
          end)

        case valid_snapshot do
          nil ->
            fold_all(account_id)

          snapshot ->
            state = Snapshots.restore(snapshot.state)
            
            event_query = 
              Event
              |> Ash.Query.filter(account_id == ^account_id and version > ^snapshot.version)
              |> Ash.Query.sort(version: :asc)

            case Ash.read(event_query) do
              {:ok, events} ->
                Fold.replay(state, events)

              {:error, reason} ->
                {:error, reason}
            end
        end

      _ ->
        fold_all(account_id)
    end
  end
end
