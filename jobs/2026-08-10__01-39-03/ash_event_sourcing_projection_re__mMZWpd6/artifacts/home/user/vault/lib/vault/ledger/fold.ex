defmodule Vault.Ledger.Fold do
  @moduledoc """
  The pure, side-effect free fold from an `Vault.Ledger.Event` stream to an
  `Vault.Ledger.AccountState`. Never reads or writes any storage.
  """

  alias Vault.Ledger.AccountState

  @doc "Returns the empty starting state for `account_id`."
  @spec initial(String.t()) :: AccountState.t()
  def initial(account_id) do
    %AccountState{account_id: account_id}
  end

  @doc """
  Applies a single event to a state, returning `{:ok, new_state}` or
  `{:error, reason}`.
  """
  @spec apply_event(AccountState.t(), Vault.Ledger.Event.t()) ::
          {:ok, AccountState.t()} | {:error, term()}
  def apply_event(%AccountState{} = state, event) do
    cond do
      not is_nil(state.account_id) and state.account_id != event.account_id ->
        {:error, {:account_mismatch, state.account_id, event.account_id}}

      event.version != state.version + 1 ->
        {:error, {:version_gap, state.version + 1, event.version}}

      true ->
        case event.payload do
          %Ash.Union{type: type, value: value} ->
            apply_member(type, value, state, event)

          _other ->
            {:error, {:unknown_event_type, nil}}
        end
    end
  end

  @doc """
  Folds a list of events (ascending by `sequence`) onto a starting state.

  Returns `{:ok, state}` for an empty list, stops at the first failure and
  returns it verbatim, and rejects out-of-order input before applying
  anything.
  """
  @spec replay(AccountState.t(), [Vault.Ledger.Event.t()]) ::
          {:ok, AccountState.t()} | {:error, term()}
  def replay(state, []), do: {:ok, state}

  def replay(state, events) do
    case first_out_of_order_index(events) do
      nil ->
        Enum.reduce_while(events, {:ok, state}, fn event, {:ok, acc} ->
          case apply_event(acc, event) do
            {:ok, new_state} -> {:cont, {:ok, new_state}}
            {:error, _reason} = error -> {:halt, error}
          end
        end)

      index ->
        {:error, {:out_of_order, index}}
    end
  end

  defp first_out_of_order_index(events) do
    events
    |> Enum.with_index()
    |> Enum.chunk_every(2, 1, :discard)
    |> Enum.find_value(fn [{prev, _prev_idx}, {curr, curr_idx}] ->
      if curr.sequence > prev.sequence, do: nil, else: curr_idx
    end)
  end

  defp apply_member(:account_opened, payload, state, event) do
    if state.status == :absent do
      {:ok,
       finish(
         %{
           state
           | owner: payload.owner,
             balance_cents: payload.opening_balance_cents,
             status: :open
         },
         :account_opened,
         event
       )}
    else
      {:error, :already_open}
    end
  end

  defp apply_member(:deposited, payload, state, event) do
    case state.status do
      :absent ->
        {:error, :account_absent}

      :frozen ->
        {:error, :account_frozen}

      :open ->
        {:ok,
         finish(
           %{
             state
             | balance_cents: state.balance_cents + payload.amount_cents,
               deposit_count: state.deposit_count + 1
           },
           :deposited,
           event
         )}
    end
  end

  defp apply_member(:withdrawn, payload, state, event) do
    case state.status do
      :absent ->
        {:error, :account_absent}

      :frozen ->
        {:error, :account_frozen}

      :open ->
        new_balance = state.balance_cents - payload.amount_cents

        if new_balance < 0 do
          {:error, :insufficient_funds}
        else
          {:ok,
           finish(
             %{
               state
               | balance_cents: new_balance,
                 withdrawal_count: state.withdrawal_count + 1
             },
             :withdrawn,
             event
           )}
        end
    end
  end

  defp apply_member(:frozen, _payload, state, event) do
    if state.status == :open do
      {:ok, finish(%{state | status: :frozen}, :frozen, event)}
    else
      {:error, :not_open}
    end
  end

  defp apply_member(:unfrozen, _payload, state, event) do
    if state.status == :frozen do
      {:ok, finish(%{state | status: :open}, :unfrozen, event)}
    else
      {:error, :not_frozen}
    end
  end

  defp apply_member(other, _payload, _state, _event) do
    {:error, {:unknown_event_type, other}}
  end

  defp finish(state, type, event) do
    %{
      state
      | account_id: event.account_id,
        version: event.version,
        last_event_type: type,
        last_recorded_at: event.recorded_at
    }
  end
end
