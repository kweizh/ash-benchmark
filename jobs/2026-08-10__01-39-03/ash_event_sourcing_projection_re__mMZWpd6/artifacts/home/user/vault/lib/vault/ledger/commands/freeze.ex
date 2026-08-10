defmodule Vault.Ledger.Commands.Freeze do
  @moduledoc false
  use Ash.Resource.Actions.Implementation

  alias Vault.Ledger.Commands.{Snapshotter, Toolkit}

  @impl true
  def run(input, _opts, _context) do
    account_id = input.arguments.account_id
    reason = input.arguments.reason
    recorded_at = Toolkit.resolve_recorded_at(input)

    result =
      Toolkit.run_checks([
        fn -> Toolkit.check_account_exists(:account_id, account_id) end,
        fn -> Toolkit.check_open(:account_id, account_id) end
      ])

    case result do
      :ok ->
        state = Toolkit.fetch_state(account_id)

        event =
          Toolkit.append!(
            account_id,
            state.version + 1,
            %{"type" => "frozen", "reason" => reason},
            recorded_at
          )

        Snapshotter.sync(account_id)
        Toolkit.finish(:freeze, account_id, [event])

      {:error, error} ->
        {:error, error}
    end
  end
end
