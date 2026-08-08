defmodule CartPricing.Sales.Calculations.CartQuote do
  @moduledoc """
  Computes the full pricing quote for a `CartPricing.Sales.Cart`, given a
  `coupon_code` (optional) and an `as_of` timestamp (required).

  No monetary figure is ever persisted - everything here is derived, in
  exact integer arithmetic, from the cart's items and (optionally) a
  matching `CartPricing.Sales.Coupon`.
  """

  use Ash.Resource.Calculation

  require Ash.Query

  alias CartPricing.Sales.Coupon

  @bps 10_000

  @impl true
  def load(_query, _opts, _context) do
    [items: [:line_total_cents, :discounted_line_total_cents]]
  end

  @impl true
  def calculate(records, _opts, context) do
    as_of = context.arguments.as_of
    coupon_code = context.arguments[:coupon_code]
    coupon = fetch_coupon(coupon_code)

    Enum.map(records, fn cart ->
      build_quote(cart, coupon_code, coupon, as_of)
    end)
  end

  defp fetch_coupon(nil), do: nil

  defp fetch_coupon(code) do
    Coupon
    |> Ash.Query.filter(code == ^code)
    |> Ash.read!()
    |> List.first()
  end

  defp build_quote(cart, coupon_code, coupon, as_of) do
    items = cart.items || []

    gross_subtotal_cents = items |> Enum.map(& &1.line_total_cents) |> Enum.sum()
    subtotal_cents = items |> Enum.map(& &1.discounted_line_total_cents) |> Enum.sum()
    tier_discount_cents = gross_subtotal_cents - subtotal_cents
    item_count = length(items)

    {coupon_status, coupon_discount_cents} =
      resolve_coupon(coupon_code, coupon, as_of, subtotal_cents)

    discounted_subtotal_cents = subtotal_cents - coupon_discount_cents
    tax_cents = tax_for_region(discounted_subtotal_cents, cart.region)
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
  end

  defp resolve_coupon(nil, _coupon, _as_of, _subtotal_cents), do: {:none, 0}
  defp resolve_coupon(_code, nil, _as_of, _subtotal_cents), do: {:not_found, 0}

  defp resolve_coupon(_code, coupon, as_of, subtotal_cents) do
    cond do
      DateTime.compare(as_of, coupon.starts_at) == :lt ->
        {:not_yet_active, 0}

      DateTime.compare(as_of, coupon.ends_at) == :gt ->
        {:expired, 0}

      not is_nil(coupon.max_redemptions) and coupon.redemption_count >= coupon.max_redemptions ->
        {:exhausted, 0}

      subtotal_cents < coupon.min_subtotal_cents ->
        {:below_minimum, 0}

      true ->
        raw_discount = floor_div(subtotal_cents * coupon.percent_off_bps, @bps)

        discount =
          if coupon.max_discount_cents && raw_discount > coupon.max_discount_cents do
            coupon.max_discount_cents
          else
            raw_discount
          end

        {:applied, discount}
    end
  end

  defp tax_for_region(base_cents, :us_ca), do: round_half_away_from_zero(base_cents, 925)
  defp tax_for_region(base_cents, :us_or), do: round_half_away_from_zero(base_cents, 0)
  defp tax_for_region(base_cents, :eu_de), do: round_half_to_even(base_cents, 1900)
  defp tax_for_region(base_cents, :jp_13), do: round_truncate(base_cents, 1000)

  defp round_half_away_from_zero(base_cents, rate_bps) do
    numerator = base_cents * rate_bps
    sign = if numerator < 0, do: -1, else: 1
    abs_numerator = abs(numerator)

    quotient = div(abs_numerator, @bps)
    remainder = rem(abs_numerator, @bps)

    quotient = if 2 * remainder >= @bps, do: quotient + 1, else: quotient

    sign * quotient
  end

  defp round_half_to_even(base_cents, rate_bps) do
    numerator = base_cents * rate_bps
    sign = if numerator < 0, do: -1, else: 1
    abs_numerator = abs(numerator)

    quotient = div(abs_numerator, @bps)
    remainder = rem(abs_numerator, @bps)

    quotient =
      cond do
        2 * remainder > @bps -> quotient + 1
        2 * remainder < @bps -> quotient
        rem(quotient, 2) == 0 -> quotient
        true -> quotient + 1
      end

    sign * quotient
  end

  defp round_truncate(base_cents, rate_bps) do
    div(base_cents * rate_bps, @bps)
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
