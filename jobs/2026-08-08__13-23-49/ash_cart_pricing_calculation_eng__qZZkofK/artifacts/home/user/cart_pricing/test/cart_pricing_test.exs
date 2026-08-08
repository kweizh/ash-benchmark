defmodule CartPricingTest do
  use ExUnit.Case
  require Ash.Query

  setup do
    # Since we are using ETS, we should clean up the tables before each test to ensure a clean state.
    # ETS table names default to the resource names.
    # We can use Ash.DataLayer.Ets.Info or just delete all records.
    # Let's delete all records by reading and destroying them.
    # Wait, we can just delete from the ETS tables directly or read and bulk destroy.
    # Reading and destroying is safe and standard:
    for resource <- [CartPricing.Sales.CartItem, CartPricing.Sales.Cart, CartPricing.Sales.Coupon] do
      resource
      |> Ash.read!()
      |> Enum.each(&Ash.destroy!/1)
    end

    :ok
  end

  test "creates and validates a cart" do
    # Valid cart creation
    cart = CartPricing.Sales.create_cart!(%{reference: "cart-1", region: :us_ca})
    assert cart.reference == "cart-1"
    assert cart.region == :us_ca
    assert is_binary(cart.id)

    # Invalid region should fail
    assert_raise Ash.Error.Invalid, fn ->
      CartPricing.Sales.create_cart!(%{reference: "cart-2", region: :invalid_region})
    end
  end

  test "creates and validates a cart item" do
    cart = CartPricing.Sales.create_cart!(%{reference: "cart-1", region: :us_ca})

    # Valid cart item
    item =
      CartPricing.Sales.create_cart_item!(%{
        sku: "SKU-1",
        unit_price_cents: 1000,
        quantity: 2,
        cart_id: cart.id
      })

    assert item.sku == "SKU-1"
    assert item.unit_price_cents == 1000
    assert item.quantity == 2
    assert item.cart_id == cart.id

    # Invalid quantity (< 1) should fail
    assert_raise Ash.Error.Invalid, fn ->
      CartPricing.Sales.create_cart_item!(%{
        sku: "SKU-2",
        unit_price_cents: 1000,
        quantity: 0,
        cart_id: cart.id
      })
    end
  end

  test "creates a coupon" do
    starts_at = ~U[2026-08-01 00:00:00Z]
    ends_at = ~U[2026-08-31 23:59:59Z]

    coupon =
      CartPricing.Sales.create_coupon!(%{
        code: "SAVE10",
        percent_off_bps: 1000,
        starts_at: starts_at,
        ends_at: ends_at,
        max_redemptions: 100,
        redemption_count: 5,
        min_subtotal_cents: 5000,
        max_discount_cents: 2000
      })

    assert coupon.code == "SAVE10"
    assert coupon.percent_off_bps == 1000
    assert coupon.starts_at == starts_at
    assert coupon.ends_at == ends_at
    assert coupon.max_redemptions == 100
    assert coupon.redemption_count == 5
    assert coupon.min_subtotal_cents == 5000
    assert coupon.max_discount_cents == 2000
  end

  test "derived fields on CartItem: line_total_cents, tier_discount_bps, discounted_line_total_cents" do
    cart = CartPricing.Sales.create_cart!(%{reference: "cart-1", region: :us_ca})

    # Tier discount bps:
    # 1–4 → 0
    # 5–9 → 500
    # 10–24 → 1000
    # 25+ → 1500

    # Case 1: quantity = 1, unit_price = 100
    # line_total = 100, tier_discount = 0, discounted_line_total = 100
    item1 =
      CartPricing.Sales.create_cart_item!(%{
        sku: "S1",
        unit_price_cents: 100,
        quantity: 1,
        cart_id: cart.id
      })

    # Load calculations
    item1 =
      Ash.load!(item1, [:line_total_cents, :tier_discount_bps, :discounted_line_total_cents])

    assert item1.line_total_cents == 100
    assert item1.tier_discount_bps == 0
    assert item1.discounted_line_total_cents == 100

    # Case 2: quantity = 5, unit_price = 1000
    # line_total = 5000, tier_discount = 500 (5%), discounted_line_total = 5000 - floor(5000 * 500 / 10000) = 5000 - 250 = 4750
    item2 =
      CartPricing.Sales.create_cart_item!(%{
        sku: "S2",
        unit_price_cents: 1000,
        quantity: 5,
        cart_id: cart.id
      })

    item2 =
      Ash.load!(item2, [:line_total_cents, :tier_discount_bps, :discounted_line_total_cents])

    assert item2.line_total_cents == 5000
    assert item2.tier_discount_bps == 500
    assert item2.discounted_line_total_cents == 4750

    # Case 3: quantity = 10, unit_price = 250
    # line_total = 2500, tier_discount = 1000 (10%), discounted_line_total = 2500 - 250 = 2250
    item3 =
      CartPricing.Sales.create_cart_item!(%{
        sku: "S3",
        unit_price_cents: 250,
        quantity: 10,
        cart_id: cart.id
      })

    item3 =
      Ash.load!(item3, [:line_total_cents, :tier_discount_bps, :discounted_line_total_cents])

    assert item3.line_total_cents == 2500
    assert item3.tier_discount_bps == 1000
    assert item3.discounted_line_total_cents == 2250

    # Case 4: quantity = 25, unit_price = 10
    # line_total = 250, tier_discount = 1500 (15%), discounted_line_total = 250 - floor(250 * 1500 / 10000) = 250 - 37 = 213
    item4 =
      CartPricing.Sales.create_cart_item!(%{
        sku: "S4",
        unit_price_cents: 10,
        quantity: 25,
        cart_id: cart.id
      })

    item4 =
      Ash.load!(item4, [:line_total_cents, :tier_discount_bps, :discounted_line_total_cents])

    assert item4.line_total_cents == 250
    assert item4.tier_discount_bps == 1500
    assert item4.discounted_line_total_cents == 213

    # Case 5: Usable inside query filter and sort
    # Let's filter items with line_total_cents > 1000
    filtered =
      CartPricing.Sales.CartItem
      |> Ash.Query.filter(line_total_cents > 1000)
      |> Ash.read!()

    # item2 and item3
    assert length(filtered) == 2
    assert Enum.any?(filtered, &(&1.sku == "S2"))
    assert Enum.any?(filtered, &(&1.sku == "S3"))

    # Let's filter items with tier_discount_bps == 1000
    filtered_discount =
      CartPricing.Sales.CartItem
      |> Ash.Query.filter(tier_discount_bps == 1000)
      |> Ash.read!()

    assert length(filtered_discount) == 1
    assert hd(filtered_discount).sku == "S3"

    # Let's sort items by line_total_cents desc
    sorted =
      CartPricing.Sales.CartItem
      |> Ash.Query.sort(line_total_cents: :desc)
      |> Ash.read!()

    assert Enum.map(sorted, & &1.sku) == ["S2", "S3", "S4", "S1"]
  end

  test "item_count aggregate on Cart" do
    cart = CartPricing.Sales.create_cart!(%{reference: "cart-1", region: :us_ca})
    cart = Ash.load!(cart, :item_count)
    assert cart.item_count == 0

    CartPricing.Sales.create_cart_item!(%{
      sku: "S1",
      unit_price_cents: 100,
      quantity: 1,
      cart_id: cart.id
    })

    CartPricing.Sales.create_cart_item!(%{
      sku: "S2",
      unit_price_cents: 200,
      quantity: 2,
      cart_id: cart.id
    })

    cart = Ash.load!(cart, :item_count)
    assert cart.item_count == 2

    # Query filter on item_count
    filtered =
      CartPricing.Sales.Cart
      |> Ash.Query.filter(item_count > 1)
      |> Ash.read!()

    assert length(filtered) == 1
    assert hd(filtered).id == cart.id
  end

  test "pricing_quote: empty cart" do
    cart = CartPricing.Sales.create_cart!(%{reference: "cart-1", region: :us_ca})
    as_of = ~U[2026-08-08 12:00:00Z]

    cart = Ash.load!(cart, pricing_quote: %{as_of: as_of})
    quote = cart.pricing_quote

    assert quote.gross_subtotal_cents == 0
    assert quote.tier_discount_cents == 0
    assert quote.subtotal_cents == 0
    assert quote.coupon_status == :none
    assert quote.coupon_discount_cents == 0
    assert quote.discounted_subtotal_cents == 0
    assert quote.tax_cents == 0
    assert quote.total_cents == 0
    assert quote.item_count == 0
  end

  test "pricing_quote: region tax rounding rules" do
    # We will test each region's tax rounding with specific subtotal values.
    # Let's create a cart for each region, and add an item such that discounted_subtotal_cents is 150.
    # 1. :us_ca: 9.25% tax. 150 * 925 / 10000 = 13.875. Half away from zero -> 14.
    # 2. :us_or: 0% tax. -> 0.
    # 3. :eu_de: 19.00% tax. 150 * 1900 / 10000 = 28.5. Half to even -> 28. (28 is even)
    #    Let's also test subtotal 250 for :eu_de. 250 * 1900 / 10000 = 47.5. Half to even -> 48. (48 is even)
    # 4. :jp_13: 10.00% tax. 150 * 1000 / 10000 = 15.
    #    Let's also test subtotal 155. 155 * 1000 / 10000 = 15.5. Truncate toward zero -> 15.

    as_of = ~U[2026-08-08 12:00:00Z]

    # US CA
    cart_ca = CartPricing.Sales.create_cart!(%{reference: "ca", region: :us_ca})

    CartPricing.Sales.create_cart_item!(%{
      sku: "S1",
      unit_price_cents: 150,
      quantity: 1,
      cart_id: cart_ca.id
    })

    cart_ca = Ash.load!(cart_ca, pricing_quote: %{as_of: as_of})
    assert cart_ca.pricing_quote.discounted_subtotal_cents == 150
    assert cart_ca.pricing_quote.tax_cents == 14
    assert cart_ca.pricing_quote.total_cents == 164

    # US OR
    cart_or = CartPricing.Sales.create_cart!(%{reference: "or", region: :us_or})

    CartPricing.Sales.create_cart_item!(%{
      sku: "S1",
      unit_price_cents: 150,
      quantity: 1,
      cart_id: cart_or.id
    })

    cart_or = Ash.load!(cart_or, pricing_quote: %{as_of: as_of})
    assert cart_or.pricing_quote.discounted_subtotal_cents == 150
    assert cart_or.pricing_quote.tax_cents == 0
    assert cart_or.pricing_quote.total_cents == 150

    # EU DE
    cart_de1 = CartPricing.Sales.create_cart!(%{reference: "de1", region: :eu_de})

    CartPricing.Sales.create_cart_item!(%{
      sku: "S1",
      unit_price_cents: 150,
      quantity: 1,
      cart_id: cart_de1.id
    })

    cart_de1 = Ash.load!(cart_de1, pricing_quote: %{as_of: as_of})
    assert cart_de1.pricing_quote.discounted_subtotal_cents == 150
    assert cart_de1.pricing_quote.tax_cents == 28
    assert cart_de1.pricing_quote.total_cents == 178

    cart_de2 = CartPricing.Sales.create_cart!(%{reference: "de2", region: :eu_de})

    CartPricing.Sales.create_cart_item!(%{
      sku: "S1",
      unit_price_cents: 250,
      quantity: 1,
      cart_id: cart_de2.id
    })

    cart_de2 = Ash.load!(cart_de2, pricing_quote: %{as_of: as_of})
    assert cart_de2.pricing_quote.discounted_subtotal_cents == 250
    assert cart_de2.pricing_quote.tax_cents == 48
    assert cart_de2.pricing_quote.total_cents == 298

    # JP 13
    cart_jp1 = CartPricing.Sales.create_cart!(%{reference: "jp1", region: :jp_13})

    CartPricing.Sales.create_cart_item!(%{
      sku: "S1",
      unit_price_cents: 150,
      quantity: 1,
      cart_id: cart_jp1.id
    })

    cart_jp1 = Ash.load!(cart_jp1, pricing_quote: %{as_of: as_of})
    assert cart_jp1.pricing_quote.discounted_subtotal_cents == 150
    assert cart_jp1.pricing_quote.tax_cents == 15
    assert cart_jp1.pricing_quote.total_cents == 165

    cart_jp2 = CartPricing.Sales.create_cart!(%{reference: "jp2", region: :jp_13})

    CartPricing.Sales.create_cart_item!(%{
      sku: "S1",
      unit_price_cents: 155,
      quantity: 1,
      cart_id: cart_jp2.id
    })

    cart_jp2 = Ash.load!(cart_jp2, pricing_quote: %{as_of: as_of})
    assert cart_jp2.pricing_quote.discounted_subtotal_cents == 155
    assert cart_jp2.pricing_quote.tax_cents == 15
    assert cart_jp2.pricing_quote.total_cents == 170
  end

  test "pricing_quote: coupon status resolution" do
    # Coupon: code="SAVE10", 10% off (1000 bps), starts_at=Aug 5, ends_at=Aug 15, max_redemptions=5, min_subtotal_cents=1000, max_discount_cents=500
    starts_at = ~U[2026-08-05 00:00:00Z]
    ends_at = ~U[2026-08-15 23:59:59Z]

    coupon =
      CartPricing.Sales.create_coupon!(%{
        code: "SAVE10",
        percent_off_bps: 1000,
        starts_at: starts_at,
        ends_at: ends_at,
        max_redemptions: 5,
        redemption_count: 2,
        min_subtotal_cents: 1000,
        max_discount_cents: 500
      })

    cart = CartPricing.Sales.create_cart!(%{reference: "cart-1", region: :us_ca})

    CartPricing.Sales.create_cart_item!(%{
      sku: "S1",
      unit_price_cents: 2000,
      quantity: 1,
      cart_id: cart.id
    })

    # Rule 1: coupon_code is nil -> :none, discount 0
    cart_loaded =
      Ash.load!(cart, pricing_quote: %{coupon_code: nil, as_of: ~U[2026-08-08 12:00:00Z]})

    assert cart_loaded.pricing_quote.coupon_status == :none
    assert cart_loaded.pricing_quote.coupon_discount_cents == 0

    # Rule 2: no coupon has that code -> :not_found, discount 0
    cart_loaded =
      Ash.load!(cart, pricing_quote: %{coupon_code: "INVALID", as_of: ~U[2026-08-08 12:00:00Z]})

    assert cart_loaded.pricing_quote.coupon_status == :not_found
    assert cart_loaded.pricing_quote.coupon_discount_cents == 0

    # Rule 3: as_of is strictly before starts_at -> :not_yet_active, discount 0
    cart_loaded =
      Ash.load!(cart, pricing_quote: %{coupon_code: "SAVE10", as_of: ~U[2026-08-04 23:59:59Z]})

    assert cart_loaded.pricing_quote.coupon_status == :not_yet_active
    assert cart_loaded.pricing_quote.coupon_discount_cents == 0

    # Rule 4: as_of is strictly after ends_at -> :expired, discount 0
    cart_loaded =
      Ash.load!(cart, pricing_quote: %{coupon_code: "SAVE10", as_of: ~U[2026-08-16 00:00:00Z]})

    assert cart_loaded.pricing_quote.coupon_status == :expired
    assert cart_loaded.pricing_quote.coupon_discount_cents == 0

    # Rule 5: redemption_count >= max_redemptions -> :exhausted, discount 0
    # Let's update the coupon's redemption_count to 5
    coupon
    |> Ash.Changeset.for_update(:update, %{redemption_count: 5})
    |> Ash.update!()

    cart_loaded =
      Ash.load!(cart, pricing_quote: %{coupon_code: "SAVE10", as_of: ~U[2026-08-08 12:00:00Z]})

    assert cart_loaded.pricing_quote.coupon_status == :exhausted
    assert cart_loaded.pricing_quote.coupon_discount_cents == 0

    # Restore redemption_count to 2
    coupon
    |> Ash.Changeset.for_update(:update, %{redemption_count: 2})
    |> Ash.update!()

    # Rule 6: subtotal_cents < min_subtotal_cents -> :below_minimum, discount 0
    # Let's create a cart with smaller subtotal (e.g. 500 cents)
    cart_small = CartPricing.Sales.create_cart!(%{reference: "cart-small", region: :us_ca})

    CartPricing.Sales.create_cart_item!(%{
      sku: "S1",
      unit_price_cents: 500,
      quantity: 1,
      cart_id: cart_small.id
    })

    cart_small_loaded =
      Ash.load!(cart_small,
        pricing_quote: %{coupon_code: "SAVE10", as_of: ~U[2026-08-08 12:00:00Z]}
      )

    assert cart_small_loaded.pricing_quote.coupon_status == :below_minimum
    assert cart_small_loaded.pricing_quote.coupon_discount_cents == 0

    # Rule 7: otherwise -> :applied
    # Subtotal is 2000. 10% of 2000 = 200. Max discount is 500, so computed 200 <= 500. Discount should be 200.
    cart_loaded =
      Ash.load!(cart, pricing_quote: %{coupon_code: "SAVE10", as_of: ~U[2026-08-08 12:00:00Z]})

    assert cart_loaded.pricing_quote.coupon_status == :applied
    assert cart_loaded.pricing_quote.coupon_discount_cents == 200

    # Let's test max_discount cap.
    # Subtotal is 6000. 10% of 6000 = 600. Max discount is 500, so computed 600 > 500. Discount should be capped at 500.
    cart_large = CartPricing.Sales.create_cart!(%{reference: "cart-large", region: :us_ca})

    CartPricing.Sales.create_cart_item!(%{
      sku: "S1",
      unit_price_cents: 6000,
      quantity: 1,
      cart_id: cart_large.id
    })

    cart_large_loaded =
      Ash.load!(cart_large,
        pricing_quote: %{coupon_code: "SAVE10", as_of: ~U[2026-08-08 12:00:00Z]}
      )

    assert cart_large_loaded.pricing_quote.coupon_status == :applied
    assert cart_large_loaded.pricing_quote.coupon_discount_cents == 500
  end

  test "loading contract: multiple loads and list operations" do
    # - pricing_quote must be obtainable while reading carts and on already fetched structs.
    # - Loading a list of carts in one operation must give every cart its own quote, correctly paired with that cart, whatever order the carts were read in.
    # - The same cart or list of carts must be loadable more than once with different inputs.

    cart1 = CartPricing.Sales.create_cart!(%{reference: "cart-1", region: :us_ca})

    CartPricing.Sales.create_cart_item!(%{
      sku: "S1",
      unit_price_cents: 1000,
      quantity: 1,
      cart_id: cart1.id
    })

    cart2 = CartPricing.Sales.create_cart!(%{reference: "cart-2", region: :eu_de})

    CartPricing.Sales.create_cart_item!(%{
      sku: "S1",
      unit_price_cents: 2000,
      quantity: 1,
      cart_id: cart2.id
    })

    as_of = ~U[2026-08-08 12:00:00Z]

    # 1. Obtainable while reading carts
    query =
      CartPricing.Sales.Cart
      |> Ash.Query.load(pricing_quote: %{as_of: as_of})

    carts = Ash.read!(query)
    assert length(carts) == 2

    cart1_loaded = Enum.find(carts, &(&1.id == cart1.id))
    cart2_loaded = Enum.find(carts, &(&1.id == cart2.id))

    assert cart1_loaded.pricing_quote.subtotal_cents == 1000
    assert cart2_loaded.pricing_quote.subtotal_cents == 2000

    # 2. Obtainable on already fetched structs with no loads at all
    cart1_fetched = CartPricing.Sales.get_cart!(cart1.id)
    cart1_with_quote = Ash.load!(cart1_fetched, pricing_quote: %{as_of: as_of})
    assert cart1_with_quote.pricing_quote.subtotal_cents == 1000

    # 3. Loading a list of carts in one operation
    list_fetched = [cart1_fetched, CartPricing.Sales.get_cart!(cart2.id)]
    list_loaded = Ash.load!(list_fetched, pricing_quote: %{as_of: as_of})

    c1 = Enum.find(list_loaded, &(&1.id == cart1.id))
    c2 = Enum.find(list_loaded, &(&1.id == cart2.id))
    assert c1.pricing_quote.subtotal_cents == 1000
    assert c2.pricing_quote.subtotal_cents == 2000

    # 4. Same cart loadable more than once with different inputs
    cart_with_quote_a =
      Ash.load!(cart1_fetched, pricing_quote: %{as_of: as_of, coupon_code: "COUPON_A"})

    cart_with_quote_b =
      Ash.load!(cart1_fetched, pricing_quote: %{as_of: as_of, coupon_code: "COUPON_B"})

    assert cart_with_quote_a.pricing_quote.coupon_status == :not_found
    assert cart_with_quote_b.pricing_quote.coupon_status == :not_found
  end
end
