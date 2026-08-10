defmodule Vault.Ledger.Commands.Transfer do
  @moduledoc false
  use Ash.Resource.Actions.Implementation

  alias Vault.Ledger.Commands.{Snapshotter, Toolkit}

  @impl true
  def run(input, _opts, _context) do
    from_id = input.arguments.from_account_id
    to_id = input.arguments.to_account_id
    amount_cents = input.arguments.amount_cents
    recorded_at = Toolkit.resolve_recorded_at(input)

    result =
      Toolkit.run_checks([
        fn -> Toolkit.check_positive(:amount_cents, amount_cents) end,
        fn ->
          Toolkit.check_different(
            :to_account_id,
            from_id,
            to_id,
            "cannot transfer to the same account"
          )
        end,
        fn -> Toolkit.check_account_exists(:from_account_id, from_id) end,
        fn -> Toolkit.check_account_exists(:to_account_id, to_id) end,
        fn -> Toolkit.check_not_frozen(:from_account_id, from_id) end,
        fn -> Toolkit.check_not_frozen(:to_account_id, to_id) end,
        fn -> Toolkit.check_sufficient_funds(:amount_cents, from_id, amount_cents) end
      ])

    case result do
      :ok ->
        from_state = Toolkit.fetch_state(from_id)

        withdraw_event =
          Toolkit.append!(
            from_id,
            from_state.version + 1,
            %{"type" => "withdrawn", "amount_cents" => amount_cents},
            recorded_at
          )

        to_state = Toolkit.fetch_state(to_id)

        deposit_event =
          Toolkit.append!(
            to_id,
            to_state.version + 1,
            %{"type" => "deposited", "amount_cents" => amount_cents},
            recorded_at
          )

        Snapshotter.sync(from_id)
        Snapshotter.sync(to_id)

        Toolkit.finish(:transfer, from_id, [withdraw_event, deposit_event])

      {:error, error} ->
        {:error, error}
    end
  end
end
