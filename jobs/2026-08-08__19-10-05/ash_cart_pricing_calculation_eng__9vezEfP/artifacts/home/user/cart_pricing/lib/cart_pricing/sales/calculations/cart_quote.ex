defmodule CartPricing.Sales.Calculations.CartQuote do
  use Ash.Resource.Calculation

  require Ash.Query

  @regions %{
    us_ca: %{rate_bps: 925, rounding: :half_away_from_zero},
    us_or: %{rate_bps: 0, rounding: :half_away_from_zero},
    eu_de: %{rate_bps: 1900, rounding: :half_to_even},
    jp_13: %{rate_bps: 1000, rounding: :truncate_toward_zero}
  }

  @impl true
  def load(_query, _opts, _context) do
    [:region, items: [:line_total_cents, :discounted_line_total_cents]]
  end

  @impl true
  def calculate(records, _opts, %{arguments: %{coupon_code: coupon_code, as_of: as_of}}) do
    # Pre-load all coupons for the codes we might need
    coupon =
      case coupon_code do
        nil ->
          nil

        code ->
          CartPricing.Sales.Coupon
          |> Ash.Query.filter(code == ^code)
          |> Ash.read!()
          |> List.first()
      end

    Enum.map(records, fn cart ->
      items = cart.items || []

      gross_subtotal_cents =
        Enum.reduce(items, 0, fn item, acc ->
          line_total = item.line_total_cents || 0
          acc + line_total
        end)

      subtotal_cents =
        Enum.reduce(items, 0, fn item, acc ->
          discounted = item.discounted_line_total_cents || 0
          acc + discounted
        end)

      tier_discount_cents = gross_subtotal_cents - subtotal_cents
      item_count = length(items)

      {coupon_status, coupon_discount_cents} =
        resolve_coupon(coupon_code, coupon, as_of, subtotal_cents)

      discounted_subtotal_cents = subtotal_cents - coupon_discount_cents

      region_config = Map.fetch!(@regions, cart.region)
      tax_cents = compute_tax(discounted_subtotal_cents, region_config)

      total_cents = discounted_subtotal_cents + tax_cents

      %{
        gross_subtotal_cents: gross_subtotal_cents,
        tier_discount_cents: tier_discount_cents,
        subtotal_cents: subtotal_cents,
        coupon_status: coupon_status,
        coupon_discount_cents: coupon_discount_cents,
        discounted_subtotal_cents: discounted_subtotal_cents,
        tax_cents: tax_cents,
        total_cents: total_cents,
        item_count: item_count
      }
    end)
  end

  # Rule 1: coupon_code is nil → :none
  defp resolve_coupon(nil, _coupon, _as_of, _subtotal_cents) do
    {:none, 0}
  end

  # Rule 2: no coupon has that code → :not_found
  defp resolve_coupon(_coupon_code, nil, _as_of, _subtotal_cents) do
    {:not_found, 0}
  end

  # Rule 3-7: coupon exists, check rules in order
  defp resolve_coupon(_coupon_code, coupon, as_of, subtotal_cents) do
    cond do
      # Rule 3: as_of strictly before starts_at
      DateTime.compare(as_of, coupon.starts_at) == :lt ->
        {:not_yet_active, 0}

      # Rule 4: as_of strictly after ends_at
      DateTime.compare(as_of, coupon.ends_at) == :gt ->
        {:expired, 0}

      # Rule 5: max_redemptions not nil and redemption_count >= max_redemptions
      not is_nil(coupon.max_redemptions) and coupon.redemption_count >= coupon.max_redemptions ->
        {:exhausted, 0}

      # Rule 6: subtotal_cents strictly less than min_subtotal_cents
      subtotal_cents < coupon.min_subtotal_cents ->
        {:below_minimum, 0}

      # Rule 7: applied
      true ->
        discount = floor(subtotal_cents * coupon.percent_off_bps / 10_000)

        discount =
          if not is_nil(coupon.max_discount_cents) and discount > coupon.max_discount_cents do
            coupon.max_discount_cents
          else
            discount
          end

        {:applied, discount}
    end
  end

  defp compute_tax(amount, %{rate_bps: rate_bps, rounding: rounding}) do
    apply_tax_rounding(amount * rate_bps, 10_000, rounding)
  end

  defp apply_tax_rounding(numerator, denominator, :half_away_from_zero) do
    # Divide and round half away from zero
    # For positive numbers: add denominator/2 before dividing
    # For negative numbers: subtract denominator/2 before dividing
    # But since all our amounts are non-negative, we just add denominator/2
    div(numerator + div(denominator, 2), denominator)
  end

  defp apply_tax_rounding(numerator, denominator, :half_to_even) do
    # Banker's rounding: round to nearest, ties to even
    quotient = div(numerator, denominator)
    remainder = rem(numerator, denominator)
    half = div(denominator, 2)

    cond do
      remainder > half -> quotient + 1
      remainder < half -> quotient
      # remainder == half: tie-breaking
      rem(quotient, 2) == 0 -> quotient
      true -> quotient + 1
    end
  end

  defp apply_tax_rounding(numerator, denominator, :truncate_toward_zero) do
    # Integer division already truncates toward zero for positive numbers
    # For negative numbers, we need to use a different approach
    if numerator >= 0 do
      div(numerator, denominator)
    else
      -div(-numerator, denominator)
    end
  end
end
