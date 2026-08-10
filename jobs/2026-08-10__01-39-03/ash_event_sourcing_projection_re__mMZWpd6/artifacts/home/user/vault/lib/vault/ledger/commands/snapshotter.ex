defmodule Vault.Ledger.Commands.Snapshotter do
  @moduledoc """
  Ensures every multiple-of-`Vault.Ledger.Snapshots.interval/0` version of
  an account's stream has a stored snapshot. Called by the command layer
  only -- never by the raw event append action.
  """

  require Ash.Query

  alias Vault.Ledger.{Aggregate, Fold, Snapshot, Snapshots}

  @spec sync(String.t()) :: :ok
  def sync(account_id) do
    interval = Snapshots.interval()

    Aggregate.events_for(account_id)
    |> Enum.reduce_while(Fold.initial(account_id), fn event, state ->
      case Fold.apply_event(state, event) do
        {:ok, new_state} ->
          if rem(new_state.version, interval) == 0 do
            ensure_snapshot(new_state, event.sequence)
          end

          {:cont, new_state}

        {:error, _reason} ->
          {:halt, state}
      end
    end)

    :ok
  end

  defp ensure_snapshot(state, sequence) do
    if snapshot_missing?(state.account_id, state.version) do
      Snapshot
      |> Ash.Changeset.for_create(
        :create,
        %{
          account_id: state.account_id,
          version: state.version,
          sequence: sequence,
          state: Snapshots.dump(state),
          checksum: Snapshots.checksum(state)
        },
        domain: Vault.Ledger,
        authorize?: false
      )
      |> Ash.create!()
    end
  end

  defp snapshot_missing?(account_id, version) do
    Snapshot
    |> Ash.Query.filter(account_id == ^account_id and version == ^version)
    |> Ash.read_one!(domain: Vault.Ledger, authorize?: false)
    |> is_nil()
  end
end
