defmodule Vault.Ledger.Commands.Toolkit do
  @moduledoc """
  Shared helpers used by the command implementations: precondition checks,
  event appending and result building.
  """

  alias Vault.Ledger.{Aggregate, CommandResult, Event}

  @doc "The `recorded_at` to use for a command: the argument if given, else now."
  @spec resolve_recorded_at(Ash.ActionInput.t()) :: DateTime.t()
  def resolve_recorded_at(input) do
    case input.arguments[:recorded_at] do
      nil -> DateTime.utc_now() |> DateTime.truncate(:microsecond)
      %DateTime{} = dt -> dt
    end
  end

  @spec exists?(String.t()) :: boolean()
  def exists?(account_id) do
    Aggregate.events_for(account_id) != []
  end

  @spec fetch_state(String.t()) :: Vault.Ledger.AccountState.t()
  def fetch_state(account_id) do
    case Aggregate.current(account_id) do
      {:ok, state} ->
        state

      {:error, reason} ->
        raise "unable to fold account #{inspect(account_id)}: #{inspect(reason)}"
    end
  end

  @doc "Runs a list of zero-arity checks in order, stopping at the first error."
  @spec run_checks([(-> :ok | {:error, term()})]) :: :ok | {:error, term()}
  def run_checks(checks) do
    Enum.reduce_while(checks, :ok, fn check, _acc ->
      case check.() do
        :ok -> {:cont, :ok}
        {:error, _} = error -> {:halt, error}
      end
    end)
  end

  @spec invalid(atom(), String.t(), Keyword.t()) :: Ash.Error.Action.InvalidArgument.t()
  def invalid(field, message, vars \\ []) do
    Ash.Error.Action.InvalidArgument.exception(field: field, message: message, vars: vars)
  end

  def check_positive(field, amount) do
    if is_integer(amount) and amount > 0 do
      :ok
    else
      {:error, invalid(field, "amount must be positive")}
    end
  end

  def check_non_negative(field, amount, message) do
    if is_integer(amount) and amount >= 0 do
      :ok
    else
      {:error, invalid(field, message)}
    end
  end

  def check_different(field, a, b, message) do
    if a == b do
      {:error, invalid(field, message)}
    else
      :ok
    end
  end

  def check_account_exists(field, account_id) do
    if exists?(account_id) do
      :ok
    else
      {:error, invalid(field, "account does not exist")}
    end
  end

  def check_account_missing(field, account_id) do
    if exists?(account_id) do
      {:error, invalid(field, "account already exists")}
    else
      :ok
    end
  end

  def check_not_frozen(field, account_id) do
    if fetch_state(account_id).status == :frozen do
      {:error, invalid(field, "account is frozen")}
    else
      :ok
    end
  end

  def check_open(field, account_id) do
    if fetch_state(account_id).status == :open do
      :ok
    else
      {:error, invalid(field, "account is not open")}
    end
  end

  def check_frozen_status(field, account_id) do
    if fetch_state(account_id).status == :frozen do
      :ok
    else
      {:error, invalid(field, "account is not frozen")}
    end
  end

  def check_sufficient_funds(field, account_id, amount) do
    if fetch_state(account_id).balance_cents < amount do
      {:error, invalid(field, "insufficient funds")}
    else
      :ok
    end
  end

  @spec append!(String.t(), pos_integer(), map(), DateTime.t()) :: Event.t()
  def append!(account_id, version, payload, recorded_at) do
    Event
    |> Ash.Changeset.for_create(
      :append,
      %{
        account_id: account_id,
        version: version,
        payload: payload,
        recorded_at: recorded_at
      },
      domain: Vault.Ledger,
      authorize?: false
    )
    |> Ash.create!()
  end

  @spec finish(atom(), String.t(), [Event.t()]) :: {:ok, CommandResult.t()}
  def finish(command, account_id, events) do
    {:ok, final_state} = Aggregate.current(account_id)

    {:ok,
     %CommandResult{
       command: command,
       account_id: account_id,
       appended: events,
       state: final_state
     }}
  end
end
