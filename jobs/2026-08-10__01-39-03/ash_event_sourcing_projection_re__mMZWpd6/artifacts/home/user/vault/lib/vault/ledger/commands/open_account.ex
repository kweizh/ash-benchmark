defmodule Vault.Ledger.Commands.OpenAccount do
  @moduledoc false
  use Ash.Resource.Actions.Implementation

  alias Vault.Ledger.Commands.{Snapshotter, Toolkit}

  @impl true
  def run(input, _opts, _context) do
    account_id = input.arguments.account_id
    owner = input.arguments.owner
    opening_balance_cents = input.arguments.opening_balance_cents
    recorded_at = Toolkit.resolve_recorded_at(input)

    result =
      Toolkit.run_checks([
        fn ->
          Toolkit.check_non_negative(
            :opening_balance_cents,
            opening_balance_cents,
            "opening balance must not be negative"
          )
        end,
        fn -> Toolkit.check_account_missing(:account_id, account_id) end
      ])

    case result do
      :ok ->
        event =
          Toolkit.append!(
            account_id,
            1,
            %{
              "type" => "account_opened",
              "owner" => owner,
              "opening_balance_cents" => opening_balance_cents
            },
            recorded_at
          )

        Snapshotter.sync(account_id)
        Toolkit.finish(:open_account, account_id, [event])

      {:error, error} ->
        {:error, error}
    end
  end
end
