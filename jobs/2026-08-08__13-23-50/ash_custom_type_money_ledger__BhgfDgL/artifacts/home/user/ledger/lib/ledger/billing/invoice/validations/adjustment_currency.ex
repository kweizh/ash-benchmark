defmodule Ledger.Billing.Invoice.Validations.AdjustmentCurrency do
  @moduledoc """
  Ensures the `:adjustment` argument uses the same currency as the
  invoice's subtotal.
  """
  use Ash.Resource.Validation

  @impl true
  def validate(changeset, _opts, _context) do
    adjustment = Ash.Changeset.get_argument(changeset, :adjustment)
    subtotal = changeset.data.subtotal

    if is_nil(adjustment) or is_nil(subtotal) or adjustment.currency == subtotal.currency do
      :ok
    else
      {:error,
       Ash.Error.Changes.InvalidArgument.exception(
         field: :adjustment,
         message: "must use the currency of the subtotal"
       )}
    end
  end
end
