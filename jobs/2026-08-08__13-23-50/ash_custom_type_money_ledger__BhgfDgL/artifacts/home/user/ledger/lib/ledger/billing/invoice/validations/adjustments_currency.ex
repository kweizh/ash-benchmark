defmodule Ledger.Billing.Invoice.Validations.AdjustmentsCurrency do
  @moduledoc """
  Ensures every adjustment uses the same currency as the subtotal.
  """
  use Ash.Resource.Validation

  @impl true
  def validate(changeset, _opts, _context) do
    subtotal = Ash.Changeset.get_attribute(changeset, :subtotal)
    adjustments = Ash.Changeset.get_attribute(changeset, :adjustments) || []

    if is_nil(subtotal) or Enum.all?(adjustments, &(&1.currency == subtotal.currency)) do
      :ok
    else
      {:error,
       Ash.Error.Changes.InvalidAttribute.exception(
         field: :adjustments,
         message: "must all use the currency of the subtotal"
       )}
    end
  end
end
