defmodule Vault.Ledger.Commands.Unfreeze do
  @moduledoc false
  use Ash.Resource.Actions.Implementation

  alias Vault.Ledger.Commands.{Snapshotter, Toolkit}

  @impl true
  def run(input, _opts, _context) do
    account_id = input.arguments.account_id
    note = input.arguments[:note]
    recorded_at = Toolkit.resolve_recorded_at(input)

    result =
      Toolkit.run_checks([
        fn -> Toolkit.check_account_exists(:account_id, account_id) end,
        fn -> Toolkit.check_frozen_status(:account_id, account_id) end
      ])

    case result do
      :ok ->
        state = Toolkit.fetch_state(account_id)
        payload = %{"type" => "unfrozen"} |> maybe_put_note(note)

        event =
          Toolkit.append!(
            account_id,
            state.version + 1,
            payload,
            recorded_at
          )

        Snapshotter.sync(account_id)
        Toolkit.finish(:unfreeze, account_id, [event])

      {:error, error} ->
        {:error, error}
    end
  end

  defp maybe_put_note(payload, nil), do: payload
  defp maybe_put_note(payload, note), do: Map.put(payload, "note", note)
end
