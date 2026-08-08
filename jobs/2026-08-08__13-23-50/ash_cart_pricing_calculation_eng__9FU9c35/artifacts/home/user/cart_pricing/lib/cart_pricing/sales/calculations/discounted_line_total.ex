defmodule CartPricing.Sales.Calculations.DiscountedLineTotal do
  @moduledoc """
  Computes a `CartPricing.Sales.CartItem`'s `discounted_line_total_cents`:

      line_total_cents - floor(line_total_cents * tier_discount_bps / 10_000)

  Declares its own dependencies via `load/3` so that the value can be
  requested on its own, even on a record that was fetched with nothing
  else loaded or selected.
  """

  use Ash.Resource.Calculation

  @impl true
  def load(_query, _opts, _context) do
    [:line_total_cents, :tier_discount_bps]
  end

  @impl true
  def calculate(records, _opts, _context) do
    Enum.map(records, fn record ->
      line_total = record.line_total_cents
      tier_bps = record.tier_discount_bps

      line_total - floor_div(line_total * tier_bps, 10_000)
    end)
  end

  # Exact-integer floor division, correct for any combination of signs.
  defp floor_div(numerator, denominator) do
    quotient = div(numerator, denominator)
    remainder = rem(numerator, denominator)

    if remainder != 0 and (remainder < 0) != (denominator < 0) do
      quotient - 1
    else
      quotient
    end
  end
end
