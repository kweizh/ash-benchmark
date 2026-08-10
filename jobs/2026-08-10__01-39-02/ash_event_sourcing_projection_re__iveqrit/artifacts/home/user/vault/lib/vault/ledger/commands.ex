defmodule Vault.Ledger.Commands do
  alias Vault.Ledger.Aggregate
  alias Vault.Ledger.CommandResult

  defp invalid_argument_error(field, message, value \\ nil) do
    inner = Ash.Error.Action.InvalidArgument.exception(
      field: field,
      message: message,
      value: value
    )
    Ash.Error.Invalid.exception(errors: [inner])
  end

  def run_command(command, args) do
    case check_invariants(command, args) do
      :ok ->
        execute_command(command, args)
      {:error, field, message} ->
        {:error, invalid_argument_error(field, message)}
    end
  end

  defp check_invariants(command, args) do
    if command in [:deposit, :withdraw, :transfer] and args[:amount_cents] <= 0 do
      {:error, :amount_cents, "amount must be positive"}
    else
      if command == :open_account and args[:opening_balance_cents] < 0 do
        {:error, :opening_balance_cents, "opening balance must not be negative"}
      else
        if command == :transfer and args[:from_account_id] == args[:to_account_id] do
          {:error, :to_account_id, "cannot transfer to the same account"}
        else
          case fetch_states_for_command(command, args) do
            {:error, field, message} ->
              {:error, field, message}
            {:ok, states} ->
              check_state_invariants(command, args, states)
          end
        end
      end
    end
  end

  defp fetch_states_for_command(command, args) do
    if command == :transfer do
      from_id = args[:from_account_id]
      to_id = args[:to_account_id]
      with {:ok, from_state} <- Aggregate.current(from_id),
           {:ok, to_state} <- Aggregate.current(to_id) do
        {:ok, %{from: from_state, to: to_state}}
      else
        _ -> {:ok, %{}}
      end
    else
      account_id = args[:account_id]
      case Aggregate.current(account_id) do
        {:ok, state} -> {:ok, %{primary: state}}
        _ -> {:ok, %{}}
      end
    end
  end

  defp check_state_invariants(command, args, states) do
    if command == :open_account do
      primary = states[:primary]
      if primary && primary.version > 0 do
        {:error, :account_id, "account already exists"}
      else
        :ok
      end
    else
      if command == :transfer do
        from_state = states[:from]
        to_state = states[:to]

        cond do
          from_state == nil or from_state.version == 0 ->
            {:error, :from_account_id, "account does not exist"}

          to_state == nil or to_state.version == 0 ->
            {:error, :to_account_id, "account does not exist"}

          from_state.status == :frozen ->
            {:error, :from_account_id, "account is frozen"}

          to_state.status == :frozen ->
            {:error, :to_account_id, "account is frozen"}

          from_state.balance_cents < args[:amount_cents] ->
            {:error, :amount_cents, "insufficient funds"}

          true ->
            :ok
        end
      else
        primary = states[:primary]

        cond do
          primary == nil or primary.version == 0 ->
            {:error, :account_id, "account does not exist"}

          command in [:deposit, :withdraw] and primary.status == :frozen ->
            {:error, :account_id, "account is frozen"}

          command == :freeze and primary.status != :open ->
            {:error, :account_id, "account is not open"}

          command == :unfreeze and primary.status != :frozen ->
            {:error, :account_id, "account is not frozen"}

          command == :withdraw and primary.balance_cents < args[:amount_cents] ->
            {:error, :amount_cents, "insufficient funds"}

          true ->
            :ok
        end
      end
    end
  end

  defp execute_command(command, args) do
    recorded_at = args[:recorded_at] || DateTime.utc_now()

    case command do
      :open_account ->
        account_id = args[:account_id]
        owner = args[:owner]
        opening_balance_cents = args[:opening_balance_cents] || 0

        payload = %{
          "type" => "account_opened",
          "owner" => owner,
          "opening_balance_cents" => opening_balance_cents
        }

        event = Ash.create!(Vault.Ledger.Event, %{
          account_id: account_id,
          version: 1,
          payload: payload,
          recorded_at: recorded_at
        }, action: :append)

        write_snapshots_for_account(account_id, 1)
        Vault.Ledger.Projector.catch_up()
        {:ok, final_state} = Aggregate.current(account_id)

        {:ok, %CommandResult{
          command: :open_account,
          account_id: account_id,
          appended: [event],
          state: final_state
        }}

      :deposit ->
        account_id = args[:account_id]
        amount_cents = args[:amount_cents]

        {:ok, state} = Aggregate.current(account_id)
        next_version = state.version + 1

        payload = %{
          "type" => "deposited",
          "amount_cents" => amount_cents
        }

        event = Ash.create!(Vault.Ledger.Event, %{
          account_id: account_id,
          version: next_version,
          payload: payload,
          recorded_at: recorded_at
        }, action: :append)

        write_snapshots_for_account(account_id, next_version)
        Vault.Ledger.Projector.catch_up()
        {:ok, final_state} = Aggregate.current(account_id)

        {:ok, %CommandResult{
          command: :deposit,
          account_id: account_id,
          appended: [event],
          state: final_state
        }}

      :withdraw ->
        account_id = args[:account_id]
        amount_cents = args[:amount_cents]

        {:ok, state} = Aggregate.current(account_id)
        next_version = state.version + 1

        payload = %{
          "type" => "withdrawn",
          "amount_cents" => amount_cents
        }

        event = Ash.create!(Vault.Ledger.Event, %{
          account_id: account_id,
          version: next_version,
          payload: payload,
          recorded_at: recorded_at
        }, action: :append)

        write_snapshots_for_account(account_id, next_version)
        Vault.Ledger.Projector.catch_up()
        {:ok, final_state} = Aggregate.current(account_id)

        {:ok, %CommandResult{
          command: :withdraw,
          account_id: account_id,
          appended: [event],
          state: final_state
        }}

      :transfer ->
        from_id = args[:from_account_id]
        to_id = args[:to_account_id]
        amount_cents = args[:amount_cents]

        {:ok, from_state} = Aggregate.current(from_id)
        {:ok, to_state} = Aggregate.current(to_id)

        from_next_version = from_state.version + 1
        to_next_version = to_state.version + 1

        from_payload = %{
          "type" => "withdrawn",
          "amount_cents" => amount_cents
        }
        to_payload = %{
          "type" => "deposited",
          "amount_cents" => amount_cents
        }

        from_event = Ash.create!(Vault.Ledger.Event, %{
          account_id: from_id,
          version: from_next_version,
          payload: from_payload,
          recorded_at: recorded_at
        }, action: :append)

        to_event = Ash.create!(Vault.Ledger.Event, %{
          account_id: to_id,
          version: to_next_version,
          payload: to_payload,
          recorded_at: recorded_at
        }, action: :append)

        write_snapshots_for_account(from_id, from_next_version)
        write_snapshots_for_account(to_id, to_next_version)

        Vault.Ledger.Projector.catch_up()
        {:ok, final_from_state} = Aggregate.current(from_id)

        {:ok, %CommandResult{
          command: :transfer,
          account_id: from_id,
          appended: [from_event, to_event],
          state: final_from_state
        }}

      :freeze ->
        account_id = args[:account_id]
        reason = args[:reason]

        {:ok, state} = Aggregate.current(account_id)
        next_version = state.version + 1

        payload = %{
          "type" => "frozen",
          "reason" => reason
        }

        event = Ash.create!(Vault.Ledger.Event, %{
          account_id: account_id,
          version: next_version,
          payload: payload,
          recorded_at: recorded_at
        }, action: :append)

        write_snapshots_for_account(account_id, next_version)
        Vault.Ledger.Projector.catch_up()
        {:ok, final_state} = Aggregate.current(account_id)

        {:ok, %CommandResult{
          command: :freeze,
          account_id: account_id,
          appended: [event],
          state: final_state
        }}

      :unfreeze ->
        account_id = args[:account_id]
        note = args[:note]

        {:ok, state} = Aggregate.current(account_id)
        next_version = state.version + 1

        payload = %{
          "type" => "unfrozen",
          "note" => note
        }

        event = Ash.create!(Vault.Ledger.Event, %{
          account_id: account_id,
          version: next_version,
          payload: payload,
          recorded_at: recorded_at
        }, action: :append)

        write_snapshots_for_account(account_id, next_version)
        Vault.Ledger.Projector.catch_up()
        {:ok, final_state} = Aggregate.current(account_id)

        {:ok, %CommandResult{
          command: :unfreeze,
          account_id: account_id,
          appended: [event],
          state: final_state
        }}
    end
  end

  defp write_snapshots_for_account(account_id, new_version) do
    Enum.each(1..new_version, fn v ->
      if rem(v, 5) == 0 do
        require Ash.Query
        query = 
          Vault.Ledger.Snapshot
          |> Ash.Query.filter(account_id == ^account_id and version == ^v)
          |> Ash.Query.limit(1)

        case Ash.read(query) do
          {:ok, [_]} ->
            :ok

          _ ->
            event_query = 
              Vault.Ledger.Event
              |> Ash.Query.filter(account_id == ^account_id and version == ^v)
              |> Ash.Query.limit(1)

            case Ash.read(event_query) do
              {:ok, [event]} ->
                case Vault.Ledger.Projector.state_at(account_id, {:version, v}) do
                  {:ok, state_at_v} ->
                    checksum = Vault.Ledger.Snapshots.checksum(state_at_v)
                    dumped = Vault.Ledger.Snapshots.dump(state_at_v)
                    Ash.create!(Vault.Ledger.Snapshot, %{
                      account_id: account_id,
                      version: v,
                      sequence: event.sequence,
                      state: dumped,
                      checksum: checksum
                    })
                  _ ->
                    :ok
                end
              _ ->
                :ok
            end
        end
      end
    end)
  end
end
