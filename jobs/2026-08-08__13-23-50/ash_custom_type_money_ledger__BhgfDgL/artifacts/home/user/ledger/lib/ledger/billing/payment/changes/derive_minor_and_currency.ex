defmodule Ledger.Billing.Payment.Changes.DeriveMinorAndCurrency do
  @moduledoc """
  Derives `:amount_minor` and `:amount_currency` from `:amount`.
  """
  use Ash.Resource.Change

  @impl true
  def change(changeset, _opts, _context) do
    case Ash.Changeset.get_attribute(changeset, :amount) do
      %Ledger.Money{currency: currency, amount: amount} ->
        changeset
        |> Ash.Changeset.force_change_attribute(:amount_minor, amount)
        |> Ash.Changeset.force_change_attribute(:amount_currency, currency)

      _ ->
        changeset
    end
  end
end
