defmodule Vault.Ledger.Fold do
  alias Vault.Ledger.AccountState

  def initial(account_id) do
    %AccountState{account_id: account_id}
  end

  def apply_event(state, event) do
    cond do
      state.account_id != nil and event.account_id != state.account_id ->
        {:error, {:account_mismatch, state.account_id, event.account_id}}

      event.version != state.version + 1 ->
        {:error, {:version_gap, state.version + 1, event.version}}

      event.payload == nil or event.payload.type not in [:account_opened, :deposited, :withdrawn, :frozen, :unfrozen] ->
        type = if event.payload, do: event.payload.type, else: nil
        {:error, {:unknown_event_type, type}}

      true ->
        payload_type = event.payload.type
        payload_val = event.payload.value

        case payload_type do
          :account_opened ->
            if state.status == :absent do
              new_state = %{state |
                owner: payload_val.owner,
                balance_cents: payload_val.opening_balance_cents,
                status: :open
              }
              {:ok, update_common(new_state, event)}
            else
              {:error, :already_open}
            end

          :deposited ->
            case state.status do
              :open ->
                new_state = %{state |
                  balance_cents: state.balance_cents + payload_val.amount_cents,
                  deposit_count: state.deposit_count + 1
                }
                {:ok, update_common(new_state, event)}

              :absent -> {:error, :account_absent}
              :frozen -> {:error, :account_frozen}
            end

          :withdrawn ->
            case state.status do
              :open ->
                new_balance = state.balance_cents - payload_val.amount_cents
                if new_balance >= 0 do
                  new_state = %{state |
                    balance_cents: new_balance,
                    withdrawal_count: state.withdrawal_count + 1
                  }
                  {:ok, update_common(new_state, event)}
                else
                  {:error, :insufficient_funds}
                end

              :absent -> {:error, :account_absent}
              :frozen -> {:error, :account_frozen}
            end

          :frozen ->
            if state.status == :open do
              new_state = %{state |
                status: :frozen
              }
              {:ok, update_common(new_state, event)}
            else
              {:error, :not_open}
            end

          :unfrozen ->
            if state.status == :frozen do
              new_state = %{state |
                status: :open
              }
              {:ok, update_common(new_state, event)}
            else
              {:error, :not_frozen}
            end
        end
    end
  end

  def replay(state, []) do
    {:ok, state}
  end

  def replay(state, events) do
    case check_order(events) do
      :ok ->
        Enum.reduce_while(events, {:ok, state}, fn event, {:ok, current_state} ->
          case apply_event(current_state, event) do
            {:ok, next_state} -> {:cont, {:ok, next_state}}
            {:error, reason} -> {:halt, {:error, reason}}
          end
        end)

      {:error, reason} ->
        {:error, reason}
    end
  end

  defp check_order(events) do
    events
    |> Enum.with_index()
    |> Enum.reduce_while(nil, fn {event, index}, prev_seq ->
      if index == 0 do
        {:cont, event.sequence}
      else
        if event.sequence > prev_seq do
          {:cont, event.sequence}
        else
          {:halt, {:error, {:out_of_order, index}}}
        end
      end
    end)
    |> case do
      {:error, reason} -> {:error, reason}
      _ -> :ok
    end
  end

  defp update_common(state, event) do
    %{state |
      version: event.version,
      last_event_type: event.payload.type,
      last_recorded_at: event.recorded_at
    }
  end
end
