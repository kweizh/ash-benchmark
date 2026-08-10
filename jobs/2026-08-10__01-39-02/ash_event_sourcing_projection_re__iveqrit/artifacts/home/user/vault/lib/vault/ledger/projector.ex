defmodule Vault.Ledger.Projector do
  alias Vault.Ledger.Fold
  alias Vault.Ledger.AccountState

  def checkpoint do
    case Ash.get(Vault.Ledger.Checkpoint, "account_projection") do
      {:ok, cp} -> cp.sequence
      _ -> 0
    end
  end

  def catch_up do
    start_seq = checkpoint()
    require Ash.Query
    query = 
      Vault.Ledger.Event
      |> Ash.Query.filter(sequence > ^start_seq)
      |> Ash.Query.sort(sequence: :asc)

    case Ash.read(query) do
      {:ok, events} ->
        IO.inspect(Enum.map(events, &{&1.sequence, &1.version, &1.account_id}), label: "EVENTS IN CATCH_UP")
        apply_events(events, 0, start_seq)

      {:error, reason} ->
        {:error, reason}
    end
  end

  def rebuild_all do
    require Ash.Query
    query = 
      Vault.Ledger.Event
      |> Ash.Query.sort(sequence: :asc)

    case Ash.read(query) do
      {:ok, events} ->
        Vault.Ledger.Hook.run(:after_load)

        case Ash.read(Vault.Ledger.AccountProjection) do
          {:ok, projections} ->
            Enum.each(projections, fn proj -> Ash.destroy!(proj) end)
          _ ->
            :ok
        end

        case rebuild_apply_events(events, %{}, 0) do
          {:ok, final_projections_map, last_seq} ->
            Enum.each(final_projections_map, fn {_account_id, {state, seq}} ->
              upsert_projection(state, seq)
            end)

            case save_checkpoint(last_seq) do
              :ok ->
                rows_count = map_size(final_projections_map)
                {:ok, %{rows: rows_count, checkpoint: last_seq}}
              {:error, err} ->
                {:error, err}
            end

          {:error, {:fold_failed, seq, reason}, partial_states_map, last_seq} ->
            Enum.each(partial_states_map, fn {_account_id, {state, s}} ->
              upsert_projection(state, s)
            end)
            save_checkpoint(last_seq)
            {:error, {:fold_failed, seq, reason}}
        end

      {:error, reason} ->
        {:error, reason}
    end
  end

  def state_at(account_id, {:version, n}) when is_integer(n) and n >= 0 do
    if n == 0 do
      {:ok, Fold.initial(account_id)}
    else
      require Ash.Query
      query = 
        Vault.Ledger.Event
        |> Ash.Query.filter(account_id == ^account_id and version <= ^n)
        |> Ash.Query.sort(version: :asc)

      case Ash.read(query) do
        {:ok, events} ->
          fold_events_with_error_handling(account_id, events)

        {:error, reason} ->
          {:error, reason}
      end
    end
  end

  def state_at(account_id, {:timestamp, %DateTime{} = dt}) do
    require Ash.Query
    query = 
      Vault.Ledger.Event
      |> Ash.Query.filter(account_id == ^account_id and recorded_at <= ^dt)
      |> Ash.Query.sort(version: :asc)

    case Ash.read(query) do
      {:ok, events} ->
        fold_events_with_error_handling(account_id, events)

      {:error, reason} ->
        {:error, reason}
    end
  end

  def state_at(_account_id, _point) do
    {:error, :invalid_point}
  end

  def audit(account_id) do
    require Ash.Query
    query = 
      Vault.Ledger.Event
      |> Ash.Query.filter(account_id == ^account_id)
      |> Ash.Query.sort(version: :asc)

    case Ash.read(query) do
      {:ok, events} ->
        initial_state = Fold.initial(account_id)
        case audit_events(events, initial_state, []) do
          {:ok, diff_list} -> diff_list
          {:error, reason} -> {:error, reason}
        end

      {:error, reason} ->
        {:error, reason}
    end
  end

  # Helper functions

  defp projection_to_state(proj) do
    %AccountState{
      account_id: proj.account_id,
      owner: proj.owner,
      balance_cents: proj.balance_cents,
      status: proj.status,
      version: proj.version,
      deposit_count: proj.deposit_count,
      withdrawal_count: proj.withdrawal_count,
      last_event_type: nil,
      last_recorded_at: proj.last_recorded_at
    }
  end

  defp apply_events([], applied_count, last_seq) do
    case save_checkpoint(last_seq) do
      :ok -> {:ok, %{applied: applied_count, checkpoint: last_seq}}
      {:error, err} -> {:error, err}
    end
  end

  defp apply_events([event | rest], applied_count, last_seq) do
    current_proj = 
      case Ash.get(Vault.Ledger.AccountProjection, event.account_id) do
        {:ok, proj} -> proj
        _ -> nil
      end

    current_state = 
      if current_proj do
        projection_to_state(current_proj)
      else
        Fold.initial(event.account_id)
      end

    IO.inspect({event.sequence, event.version, event.account_id, current_state.version, current_state.status}, label: "APPLYING EVENT")

    case Fold.apply_event(current_state, event) do
      {:ok, next_state} ->
        case upsert_projection(next_state, event.sequence) do
          :ok ->
            apply_events(rest, applied_count + 1, event.sequence)
          {:error, err} ->
            {:error, err}
        end

      {:error, reason} ->
        IO.inspect(reason, label: "FOLD FAILED FOR EVENT #{event.sequence}")
        save_checkpoint(last_seq)
        {:error, {:fold_failed, event.sequence, reason}}
    end
  end

  defp rebuild_apply_events([], states_map, last_seq) do
    {:ok, states_map, last_seq}
  end

  defp rebuild_apply_events([event | rest], states_map, last_seq) do
    current_state = 
      case Map.get(states_map, event.account_id) do
        {state, _seq} -> state
        nil -> Fold.initial(event.account_id)
      end

    case Fold.apply_event(current_state, event) do
      {:ok, next_state} ->
        new_states_map = Map.put(states_map, event.account_id, {next_state, event.sequence})
        rebuild_apply_events(rest, new_states_map, event.sequence)

      {:error, reason} ->
        {:error, {:fold_failed, event.sequence, reason}, states_map, last_seq}
    end
  end

  defp save_checkpoint(seq) do
    res = 
      case Ash.get(Vault.Ledger.Checkpoint, "account_projection") do
        {:ok, cp} ->
          Ash.update(cp, %{sequence: seq})
        _ ->
          Ash.create(Vault.Ledger.Checkpoint, %{name: "account_projection", sequence: seq})
      end
    IO.inspect(res, label: "SAVE CHECKPOINT RESULT FOR SEQ #{seq}")
    case res do
      {:ok, _} -> :ok
      {:error, err} -> {:error, err}
    end
  end

  defp upsert_projection(state, sequence) do
    params = %{
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

    case Ash.get(Vault.Ledger.AccountProjection, state.account_id) do
      {:ok, proj} ->
        case Ash.update(proj, Map.delete(params, :account_id)) do
          {:ok, _} -> :ok
          {:error, err} -> {:error, err}
        end
      _ ->
        case Ash.create(Vault.Ledger.AccountProjection, params) do
          {:ok, _} -> :ok
          {:error, err} -> {:error, err}
        end
    end
  end

  defp fold_events_with_error_handling(account_id, events) do
    initial_state = Fold.initial(account_id)
    Enum.reduce_while(events, {:ok, initial_state}, fn event, {:ok, current_state} ->
      case Fold.apply_event(current_state, event) do
        {:ok, next_state} -> {:cont, {:ok, next_state}}
        {:error, reason} -> {:halt, {:error, {:fold_failed, event.sequence, reason}}}
      end
    end)
  end

  defp audit_events([], _state, acc) do
    {:ok, Enum.reverse(acc)}
  end

  defp audit_events([event | rest], state, acc) do
    case Fold.apply_event(state, event) do
      {:ok, next_state} ->
        entry = %{
          sequence: event.sequence,
          version: event.version,
          type: event.payload.type,
          balance_before: state.balance_cents,
          balance_after: next_state.balance_cents,
          delta_cents: next_state.balance_cents - state.balance_cents,
          status_before: state.status,
          status_after: next_state.status,
          recorded_at: event.recorded_at
        }
        audit_events(rest, next_state, [entry | acc])

      {:error, reason} ->
        {:error, {:fold_failed, event.sequence, reason}}
    end
  end
end
