defmodule CartPricing.Sales.Calculations.CartQuote do
  use Ash.Resource.Calculation
  require Ash.Query

  @impl Ash.Resource.Calculation
  def load(_query, _opts, _context) do
    [:region, items: [:line_total_cents, :discounted_line_total_cents]]
  end

  @impl Ash.Resource.Calculation
  def calculate(records, _opts, context) do
    coupon_code = context.arguments[:coupon_code]
    as_of = context.arguments[:as_of]

    # Pre-fetch coupon if coupon_code is provided
    coupon =
      if is_nil(coupon_code) do
        nil
      else
        CartPricing.Sales.Coupon
        |> Ash.Query.filter(code == ^coupon_code)
        |> Ash.read!()
        |> List.first()
      end

    quotes =
      Enum.map(records, fn record ->
        items = record.items || []
        item_count = length(items)

        gross_subtotal_cents =
          Enum.reduce(items, 0, fn item, acc ->
            acc + item.line_total_cents
          end)

        subtotal_cents =
          Enum.reduce(items, 0, fn item, acc ->
            acc + item.discounted_line_total_cents
          end)

        tier_discount_cents = gross_subtotal_cents - subtotal_cents

        {coupon_status, coupon_discount_cents} =
          cond do
            is_nil(coupon_code) ->
              {:none, 0}

            is_nil(coupon) ->
              {:not_found, 0}

            DateTime.compare(as_of, coupon.starts_at) == :lt ->
              {:not_yet_active, 0}

            DateTime.compare(as_of, coupon.ends_at) == :gt ->
              {:expired, 0}

            not is_nil(coupon.max_redemptions) and
                coupon.redemption_count >= coupon.max_redemptions ->
              {:exhausted, 0}

            subtotal_cents < coupon.min_subtotal_cents ->
              {:below_minimum, 0}

            true ->
              computed = div(subtotal_cents * coupon.percent_off_bps, 10_000)

              final_discount =
                if not is_nil(coupon.max_discount_cents) and computed > coupon.max_discount_cents do
                  coupon.max_discount_cents
                else
                  computed
                end

              {:applied, final_discount}
          end

        discounted_subtotal_cents = subtotal_cents - coupon_discount_cents

        tax_cents = round_tax(discounted_subtotal_cents, record.region)

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

    {:ok, quotes}
  end

  defp round_tax(discounted_subtotal_cents, region) do
    rate_bps =
      case region do
        :us_ca -> 925
        :us_or -> 0
        :eu_de -> 1900
        :jp_13 -> 1000
      end

    n = discounted_subtotal_cents * rate_bps
    d = 10_000

    case region do
      r when r in [:us_ca, :us_or] ->
        # half away from zero
        if n >= 0 do
          q = div(n, d)
          rem_val = rem(n, d)
          if rem_val >= 5_000, do: q + 1, else: q
        else
          n_abs = -n
          q = div(n_abs, d)
          rem_val = rem(n_abs, d)
          res = if rem_val >= 5_000, do: q + 1, else: q
          -res
        end

      :eu_de ->
        # half to even
        if n >= 0 do
          q = div(n, d)
          rem_val = rem(n, d)

          cond do
            rem_val > 5_000 ->
              q + 1

            rem_val < 5_000 ->
              q

            rem_val == 5_000 ->
              if rem(q, 2) == 0, do: q, else: q + 1
          end
        else
          n_abs = -n
          q = div(n_abs, d)
          rem_val = rem(n_abs, d)

          res =
            cond do
              rem_val > 5_000 ->
                q + 1

              rem_val < 5_000 ->
                q

              rem_val == 5_000 ->
                if rem(q, 2) == 0, do: q, else: q + 1
            end

          -res
        end

      :jp_13 ->
        # truncate toward zero
        div(n, d)
    end
  end
end
