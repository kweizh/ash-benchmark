defmodule Ledger.Billing.Invoice.Changes.AppendAdjustment do
  @moduledoc """
  Appends the `:adjustment` argument to the `:adjustments` attribute.
  """
  use Ash.Resource.Change

  @impl true
  def change(changeset, _opts, _context) do
    case Ash.Changeset.get_argument(changeset, :adjustment) do
      nil ->
        changeset

      adjustment ->
        current = Ash.Changeset.get_attribute(changeset, :adjustments) || []
        Ash.Changeset.force_change_attribute(changeset, :adjustments, current ++ [adjustment])
    end
  end
end
