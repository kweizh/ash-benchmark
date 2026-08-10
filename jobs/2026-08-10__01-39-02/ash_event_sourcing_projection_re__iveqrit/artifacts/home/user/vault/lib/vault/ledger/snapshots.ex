defmodule Vault.Ledger.Snapshots do
  alias Vault.Ledger.AccountState
  alias Vault.Ledger.Snapshot

  def interval, do: 5

  def dump(%AccountState{} = state) do
    %{
      "account_id" => state.account_id,
      "owner" => state.owner,
      "balance_cents" => state.balance_cents,
      "status" => if(state.status, do: to_string(state.status), else: nil),
      "version" => state.version,
      "deposit_count" => state.deposit_count,
      "withdrawal_count" => state.withdrawal_count,
      "last_event_type" => if(state.last_event_type, do: to_string(state.last_event_type), else: nil),
      "last_recorded_at" => if(state.last_recorded_at, do: DateTime.to_iso8601(state.last_recorded_at), else: nil)
    }
  end

  def restore(map) when is_map(map) do
    %AccountState{
      account_id: map["account_id"],
      owner: map["owner"],
      balance_cents: map["balance_cents"],
      status: if(map["status"], do: String.to_existing_atom(map["status"]), else: nil),
      version: map["version"],
      deposit_count: map["deposit_count"],
      withdrawal_count: map["withdrawal_count"],
      last_event_type: if(map["last_event_type"], do: String.to_existing_atom(map["last_event_type"]), else: nil),
      last_recorded_at: if(map["last_recorded_at"]) do
        {:ok, dt, _} = DateTime.from_iso8601(map["last_recorded_at"])
        dt
      else
        nil
      end
    }
  end

  def checksum(%AccountState{} = state) do
    status_str = if state.status, do: to_string(state.status), else: ""
    [
      state.account_id,
      state.version,
      state.balance_cents,
      status_str,
      state.deposit_count,
      state.withdrawal_count
    ]
    |> Enum.map(&to_string/1)
    |> Enum.join("|")
    |> then(fn data -> :crypto.hash(:sha256, data) end)
    |> Base.encode16(case: :lower)
  end

  def latest(account_id) do
    require Ash.Query
    query = 
      Snapshot
      |> Ash.Query.filter(account_id == ^account_id)
      |> Ash.Query.sort(version: :desc)
      |> Ash.Query.limit(1)

    case Ash.read(query) do
      {:ok, [snapshot]} -> {:ok, snapshot}
      _ -> :none
    end
  end

  def verify(%Snapshot{} = snapshot) do
    restored = restore(snapshot.state)
    cond do
      checksum(restored) != snapshot.checksum ->
        {:error, :checksum_mismatch}

      restored.version != snapshot.version ->
        {:error, :version_mismatch}

      true ->
        :ok
    end
  end
end
