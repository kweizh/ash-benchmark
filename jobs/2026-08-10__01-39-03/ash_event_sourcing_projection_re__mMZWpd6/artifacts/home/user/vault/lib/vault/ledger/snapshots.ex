defmodule Vault.Ledger.Snapshots do
  @moduledoc """
  Dump/restore/checksum helpers for `Vault.Ledger.Snapshot`, plus lookup of
  the latest snapshot for an account.
  """

  require Ash.Query

  alias Vault.Ledger.AccountState
  alias Vault.Ledger.Snapshot

  @doc "How often (in versions) a snapshot should be taken."
  @spec interval() :: pos_integer()
  def interval, do: 5

  @doc "Turns an `%AccountState{}` into the string-keyed map stored in `state`."
  @spec dump(AccountState.t()) :: map()
  def dump(%AccountState{} = state) do
    %{
      "account_id" => state.account_id,
      "owner" => state.owner,
      "balance_cents" => state.balance_cents,
      "status" => status_to_string(state.status),
      "version" => state.version,
      "deposit_count" => state.deposit_count,
      "withdrawal_count" => state.withdrawal_count,
      "last_event_type" => atom_to_string(state.last_event_type),
      "last_recorded_at" => datetime_to_string(state.last_recorded_at)
    }
  end

  @doc "The exact inverse of `dump/1`."
  @spec restore(map()) :: AccountState.t()
  def restore(map) do
    %AccountState{
      account_id: Map.get(map, "account_id"),
      owner: Map.get(map, "owner"),
      balance_cents: Map.get(map, "balance_cents"),
      status: string_to_atom(Map.get(map, "status")),
      version: Map.get(map, "version"),
      deposit_count: Map.get(map, "deposit_count"),
      withdrawal_count: Map.get(map, "withdrawal_count"),
      last_event_type: string_to_atom(Map.get(map, "last_event_type")),
      last_recorded_at: string_to_datetime(Map.get(map, "last_recorded_at"))
    }
  end

  @doc "The lowercase hex SHA-256 digest used to detect a corrupted snapshot."
  @spec checksum(AccountState.t()) :: String.t()
  def checksum(%AccountState{} = state) do
    [
      to_string(state.account_id),
      to_string(state.version),
      to_string(state.balance_cents),
      to_string(state.status),
      to_string(state.deposit_count),
      to_string(state.withdrawal_count)
    ]
    |> Enum.join("|")
    |> then(&:crypto.hash(:sha256, &1))
    |> Base.encode16(case: :lower)
  end

  @doc "The highest-version stored snapshot for `account_id`, or `:none`."
  @spec latest(String.t()) :: {:ok, Snapshot.t()} | :none
  def latest(account_id) do
    Snapshot
    |> Ash.Query.filter(account_id == ^account_id)
    |> Ash.Query.sort(version: :desc)
    |> Ash.Query.limit(1)
    |> Ash.read_one(domain: Vault.Ledger, authorize?: false)
    |> case do
      {:ok, nil} -> :none
      {:ok, snapshot} -> {:ok, snapshot}
      {:error, _} -> :none
    end
  end

  @doc """
  Verifies that a snapshot's stored checksum matches its stored state, and
  that the restored state's version matches the snapshot's version.
  """
  @spec verify(Snapshot.t()) :: :ok | {:error, :checksum_mismatch} | {:error, :version_mismatch}
  def verify(%Snapshot{} = snapshot) do
    state = restore(snapshot.state)

    cond do
      checksum(state) != snapshot.checksum -> {:error, :checksum_mismatch}
      state.version != snapshot.version -> {:error, :version_mismatch}
      true -> :ok
    end
  end

  defp status_to_string(nil), do: nil
  defp status_to_string(status), do: to_string(status)

  defp atom_to_string(nil), do: nil
  defp atom_to_string(atom), do: to_string(atom)

  defp string_to_atom(nil), do: nil
  defp string_to_atom(string) when is_binary(string), do: String.to_existing_atom(string)
  defp string_to_atom(other) when is_atom(other), do: other

  defp datetime_to_string(nil), do: nil
  defp datetime_to_string(%DateTime{} = dt), do: DateTime.to_iso8601(dt)

  defp string_to_datetime(nil), do: nil

  defp string_to_datetime(string) when is_binary(string) do
    case DateTime.from_iso8601(string) do
      {:ok, dt, _offset} -> dt
      _ -> nil
    end
  end

  defp string_to_datetime(%DateTime{} = dt), do: dt
end
