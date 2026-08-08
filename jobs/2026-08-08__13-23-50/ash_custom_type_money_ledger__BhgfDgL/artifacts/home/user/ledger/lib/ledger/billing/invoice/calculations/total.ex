defmodule Ledger.Billing.Invoice.Calculations.Total do
  @moduledoc """
  The subtotal plus every adjustment.
  """
  use Ash.Resource.Calculation

  alias Ledger.Money

  @impl true
  def load(_query, _opts, _context), do: [:subtotal, :adjustments]

  @impl true
  def calculate(records, _opts, _context) do
    Enum.map(records, fn record ->
      adjustments = record.adjustments || []

      case Money.sum([record.subtotal | adjustments], record.subtotal.currency) do
        {:ok, total} -> total
        {:error, _reason} -> nil
      end
    end)
  end
end
