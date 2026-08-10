defmodule Vault.Ledger.Commands.Withdraw do
  @moduledoc false
  use Ash.Resource.Actions.Implementation

  alias Vault.Ledger.Commands.{Snapshotter, Toolkit}

  @impl true
  def run(input, _opts, _context) do
    account_id = input.arguments.account_id
    amount_cents = input.arguments.amount_cents
    recorded_at = Toolkit.resolve_recorded_at(input)

    result =
      Toolkit.run_checks([
        fn -> Toolkit.check_positive(:amount_cents, amount_cents) end,
        fn -> Toolkit.check_account_exists(:account_id, account_id) end,
        fn -> Toolkit.check_not_frozen(:account_id, account_id) end,
        fn -> Toolkit.check_sufficient_funds(:amount_cents, account_id, amount_cents) end
      ])

    case result do
      :ok ->
        state = Toolkit.fetch_state(account_id)

        event =
          Toolkit.append!(
            account_id,
            state.version + 1,
            %{"type" => "withdrawn", "amount_cents" => amount_cents},
            recorded_at
          )

        Snapshotter.sync(account_id)
        Toolkit.finish(:withdraw, account_id, [event])

      {:error, error} ->
        {:error, error}
    end
  end
end
