defmodule Ledger.Billing.Invoice.Calculations.Balance do
  @moduledoc """
  The total minus everything paid.
  """
  use Ash.Resource.Calculation

  alias Ledger.Money

  @impl true
  def load(_query, _opts, _context), do: [:total, :paid_minor]

  @impl true
  def calculate(records, _opts, _context) do
    Enum.map(records, fn record ->
      paid = Money.new!(record.paid_minor || 0, record.total.currency)

      case Money.subtract(record.total, paid) do
        {:ok, balance} -> balance
        {:error, _reason} -> nil
      end
    end)
  end
end
