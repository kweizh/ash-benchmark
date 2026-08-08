defmodule CartPricing.Sales.Calculations.DiscountedLineTotal do
  use Ash.Resource.Calculation

  @impl true
  def load(_query, _opts, _context) do
    [:line_total_cents, :tier_discount_bps]
  end

  @impl true
  def calculate(records, _opts, _context) do
    Enum.map(records, fn record ->
      line_total = record.line_total_cents
      discount_bps = record.tier_discount_bps
      discount = floor(line_total * discount_bps / 10_000)
      line_total - discount
    end)
  end
end
