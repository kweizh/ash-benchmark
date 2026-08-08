defmodule CartPricing.Sales.Calculations.DiscountedLineTotal do
  use Ash.Resource.Calculation

  @impl Ash.Resource.Calculation
  def load(_query, _opts, _context) do
    [:line_total_cents, :tier_discount_bps]
  end

  @impl Ash.Resource.Calculation
  def calculate(records, _opts, _context) do
    values =
      Enum.map(records, fn record ->
        line_total = record.line_total_cents
        tier_discount = record.tier_discount_bps
        discount = div(line_total * tier_discount, 10_000)
        line_total - discount
      end)

    {:ok, values}
  end
end
