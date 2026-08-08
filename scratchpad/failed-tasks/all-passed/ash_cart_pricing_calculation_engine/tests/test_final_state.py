"""Final-state verification for the Ash cart pricing calculation engine task.

The verifier drops a JSON-lines ExUnit formatter plus a behaviour suite into the
executor's project and runs the real Ash runtime against the executor's
resources. Each ExUnit scenario (``T01`` ... ``T26``) is surfaced as its own
pytest test so that partial implementations are graded granularly.
"""

import json
import os
import shutil
import subprocess

import pytest

PROJECT_DIR = "/home/user/cart_pricing"
VERIFY_DIR = os.path.join(PROJECT_DIR, "test", "verification")
SUITE_PATH = os.path.join(VERIFY_DIR, "pricing_engine_test.exs")
HELPER_PATH = os.path.join(PROJECT_DIR, "test", "test_helper.exs")
RESULTS_PATH = "/tmp/exunit_results.jsonl"

TEST_HELPER_SRC = r"""
defmodule CartPricingVerify.JsonFormatter do
  @moduledoc false
  use GenServer

  @path "/tmp/exunit_results.jsonl"

  @impl true
  def init(_opts) do
    File.rm_rf(@path)
    File.touch!(@path)
    {:ok, %{}}
  end

  @impl true
  def handle_cast({:test_finished, %ExUnit.Test{} = test}, state) do
    {status, message} =
      case test.state do
        nil ->
          {"passed", ""}

        {:failed, failures} ->
          {"failed", safe_format(test, failures)}

        {:invalid, _module} ->
          {"failed", "setup_all failed for #{inspect(test.module)}"}

        {:skipped, reason} ->
          {"skipped", inspect(reason)}

        {:excluded, reason} ->
          {"skipped", inspect(reason)}

        other ->
          {"failed", inspect(other)}
      end

    line =
      Jason.encode!(%{
        "name" => to_string(test.name),
        "module" => inspect(test.module),
        "status" => status,
        "message" => String.slice(message, 0, 8000)
      })

    File.write!(@path, line <> "\n", [:append])
    {:noreply, state}
  end

  def handle_cast(_event, state), do: {:noreply, state}

  defp safe_format(test, failures) do
    ExUnit.Formatter.format_test_failure(test, failures, 1, 120, fn _kind, msg -> msg end)
  rescue
    _ -> inspect(failures)
  end
end

ExUnit.start(
  formatters: [ExUnit.CLIFormatter, CartPricingVerify.JsonFormatter],
  timeout: 120_000,
  max_failures: :infinity
)
"""

SUITE_SRC = r'''
defmodule CartPricing.Verification.PricingEngineTest do
  @moduledoc false
  use ExUnit.Case, async: false

  require Ash.Query

  alias CartPricing.Sales
  alias CartPricing.Sales.Cart
  alias CartPricing.Sales.CartItem
  alias CartPricing.Sales.Coupon

  @quote_keys [
    :coupon_discount_cents,
    :coupon_status,
    :discounted_subtotal_cents,
    :gross_subtotal_cents,
    :item_count,
    :subtotal_cents,
    :tax_cents,
    :tier_discount_cents,
    :total_cents
  ]

  @statuses [:none, :not_found, :not_yet_active, :expired, :exhausted, :below_minimum, :applied]

  defp cart!(reference, region) do
    Sales.create_cart!(%{reference: reference, region: region})
  end

  defp item!(cart, sku, unit_price_cents, quantity) do
    Sales.create_cart_item!(%{
      sku: sku,
      unit_price_cents: unit_price_cents,
      quantity: quantity,
      cart_id: cart.id
    })
  end

  defp coupon!(attrs) do
    Sales.create_coupon!(attrs)
  end

  defp items_of(cart, loads) do
    CartItem
    |> Ash.Query.filter(cart_id == ^cart.id)
    |> Ash.Query.sort(sku: :asc)
    |> Ash.Query.load(loads)
    |> Ash.read!()
  end

  defp raw_items_of(cart) do
    CartItem
    |> Ash.Query.filter(cart_id == ^cart.id)
    |> Ash.Query.sort(sku: :asc)
    |> Ash.read!()
  end

  defp quote_via_query!(cart, args) do
    [loaded] =
      Cart
      |> Ash.Query.filter(id == ^cart.id)
      |> Ash.Query.load(pricing_quote: args)
      |> Ash.read!()

    loaded.pricing_quote
  end

  defp quote_after_fetch!(cart, args) do
    fetched = Sales.get_cart!(cart.id)
    Ash.load!(fetched, pricing_quote: args).pricing_quote
  end

  defp assert_money(quote_map) do
    assert is_map(quote_map), "expected pricing_quote to be a map, got: #{inspect(quote_map)}"

    assert Enum.sort(Map.keys(quote_map)) == @quote_keys,
           "unexpected pricing_quote key set: #{inspect(Enum.sort(Map.keys(quote_map)))}"

    for key <- @quote_keys -- [:coupon_status] do
      value = Map.fetch!(quote_map, key)

      assert is_integer(value),
             "pricing_quote.#{key} must be an integer, got: #{inspect(value)}"
    end

    assert Map.fetch!(quote_map, :coupon_status) in @statuses,
           "unexpected coupon_status: #{inspect(Map.fetch!(quote_map, :coupon_status))}"

    quote_map
  end

  @march ~U[2026-03-15 12:00:00Z]

  defp march_coupon(code, extra) do
    coupon!(
      Map.merge(
        %{
          code: code,
          percent_off_bps: 1000,
          starts_at: ~U[2026-03-01 00:00:00Z],
          ends_at: ~U[2026-03-31 23:59:59Z]
        },
        extra
      )
    )
  end

  test "T01 line totals" do
    cart = cart!("t01", :us_or)
    item!(cart, "a", 1250, 3)
    item!(cart, "b", 99, 1)

    loaded = items_of(cart, :line_total_cents)
    assert Enum.map(loaded, & &1.line_total_cents) == [3750, 99]
    assert Enum.all?(loaded, &is_integer(&1.line_total_cents))

    after_fetch = Ash.load!(raw_items_of(cart), :line_total_cents)
    assert Enum.map(after_fetch, & &1.line_total_cents) == [3750, 99]
  end

  test "T02 tier table" do
    cart = cart!("t02", :us_or)
    quantities = [1, 4, 5, 9, 10, 24, 25, 100]

    quantities
    |> Enum.with_index(1)
    |> Enum.each(fn {qty, index} ->
      item!(cart, "q" <> String.pad_leading(to_string(index), 2, "0"), 100, qty)
    end)

    loaded = items_of(cart, :tier_discount_bps)

    assert Enum.map(loaded, & &1.tier_discount_bps) ==
             [0, 0, 500, 500, 1000, 1000, 1500, 1500]
  end

  test "T03 filter and sort on derived item fields" do
    cart = cart!("t03", :us_or)
    item!(cart, "s1", 500, 2)
    item!(cart, "s2", 500, 10)
    item!(cart, "s3", 80, 30)
    item!(cart, "s4", 10_000, 1)

    tiered =
      CartItem
      |> Ash.Query.filter(cart_id == ^cart.id and tier_discount_bps == 1000)
      |> Ash.read!()

    assert Enum.map(tiered, & &1.sku) == ["s2"]

    expensive =
      CartItem
      |> Ash.Query.filter(cart_id == ^cart.id and line_total_cents > 3000)
      |> Ash.read!()
      |> Enum.map(& &1.sku)
      |> Enum.sort()

    assert expensive == ["s2", "s4"]

    sorted =
      CartItem
      |> Ash.Query.filter(cart_id == ^cart.id)
      |> Ash.Query.sort(line_total_cents: :desc)
      |> Ash.read!()
      |> Enum.map(& &1.sku)

    assert sorted == ["s4", "s2", "s3", "s1"]
  end

  test "T04 composed line discount" do
    cart = cart!("t04", :us_or)
    item!(cart, "a", 333, 7)
    item!(cart, "b", 1999, 25)

    loaded = items_of(cart, [:line_total_cents, :tier_discount_bps, :discounted_line_total_cents])

    assert Enum.map(loaded, &{&1.line_total_cents, &1.tier_discount_bps, &1.discounted_line_total_cents}) ==
             [{2331, 500, 2215}, {49_975, 1500, 42_479}]

    only_discounted = items_of(cart, :discounted_line_total_cents)
    assert Enum.map(only_discounted, & &1.discounted_line_total_cents) == [2215, 42_479]

    after_fetch = Ash.load!(raw_items_of(cart), :discounted_line_total_cents)
    assert Enum.map(after_fetch, & &1.discounted_line_total_cents) == [2215, 42_479]
  end

  test "T05 item_count aggregate" do
    a = cart!("t05-a", :us_or)
    b = cart!("t05-b", :us_or)
    cart!("t05-c", :us_or)

    item!(a, "a1", 100, 1)
    item!(a, "a2", 100, 1)
    item!(a, "a3", 100, 1)
    item!(b, "b1", 100, 1)

    refs = ["t05-a", "t05-b", "t05-c"]

    loaded =
      Cart
      |> Ash.Query.filter(reference in ^refs)
      |> Ash.Query.sort(reference: :asc)
      |> Ash.Query.load(:item_count)
      |> Ash.read!()

    assert Enum.map(loaded, & &1.item_count) == [3, 1, 0]

    filtered =
      Cart
      |> Ash.Query.filter(reference in ^refs and item_count >= 2)
      |> Ash.read!()

    assert Enum.map(filtered, & &1.reference) == ["t05-a"]
  end

  test "T06 quote shape" do
    cart = cart!("t06", :us_ca)
    item!(cart, "a", 1234, 3)

    assert_money(quote_via_query!(cart, %{as_of: @march}))
    assert_money(quote_after_fetch!(cart, %{as_of: @march, coupon_code: nil}))
  end

  test "T07 no-coupon quote in a zero-tax region" do
    cart = cart!("t07", :us_or)
    item!(cart, "a", 1000, 2)
    item!(cart, "b", 250, 4)

    q = assert_money(quote_via_query!(cart, %{as_of: @march}))

    assert q.gross_subtotal_cents == 3000
    assert q.tier_discount_cents == 0
    assert q.subtotal_cents == 3000
    assert q.coupon_status == :none
    assert q.coupon_discount_cents == 0
    assert q.discounted_subtotal_cents == 3000
    assert q.tax_cents == 0
    assert q.total_cents == 3000
    assert q.item_count == 2
  end

  test "T08 mixed tiers aggregate correctly" do
    cart = cart!("t08", :us_or)
    item!(cart, "a", 700, 3)
    item!(cart, "b", 700, 5)
    item!(cart, "c", 700, 12)
    item!(cart, "d", 700, 40)

    lines = items_of(cart, [:line_total_cents, :discounted_line_total_cents])
    assert Enum.map(lines, & &1.line_total_cents) == [2100, 3500, 8400, 28_000]
    assert Enum.map(lines, & &1.discounted_line_total_cents) == [2100, 3325, 7560, 23_800]

    q = assert_money(quote_via_query!(cart, %{as_of: @march}))
    assert q.gross_subtotal_cents == 42_000
    assert q.subtotal_cents == 36_785
    assert q.tier_discount_cents == 5215
    assert q.item_count == 4
    assert q.total_cents == 36_785
  end

  test "T09 nil coupon code" do
    cart = cart!("t09", :us_or)
    item!(cart, "a", 700, 3)

    without = assert_money(quote_via_query!(cart, %{as_of: @march}))
    explicit = assert_money(quote_via_query!(cart, %{as_of: @march, coupon_code: nil}))

    assert without.coupon_status == :none
    assert without.coupon_discount_cents == 0
    assert explicit.coupon_status == :none
    assert explicit.coupon_discount_cents == 0
  end

  test "T10 unknown coupon code" do
    cart = cart!("t10", :us_or)
    item!(cart, "a", 5000, 1)
    march_coupon("SAVE10", %{})

    q = assert_money(quote_via_query!(cart, %{as_of: @march, coupon_code: "NOPE"}))
    assert q.coupon_status == :not_found
    assert q.coupon_discount_cents == 0
    assert q.total_cents == 5000
  end

  test "T11 window start boundary" do
    cart = cart!("t11", :us_or)
    item!(cart, "a", 5000, 1)
    march_coupon("WINDOW11", %{})

    before = assert_money(quote_via_query!(cart, %{as_of: ~U[2026-02-28 23:59:59Z], coupon_code: "WINDOW11"}))
    assert before.coupon_status == :not_yet_active
    assert before.coupon_discount_cents == 0
    assert before.total_cents == 5000

    at_start = assert_money(quote_via_query!(cart, %{as_of: ~U[2026-03-01 00:00:00Z], coupon_code: "WINDOW11"}))
    assert at_start.coupon_status == :applied
    assert at_start.coupon_discount_cents == 500
    assert at_start.total_cents == 4500
  end

  test "T12 window end boundary" do
    cart = cart!("t12", :us_or)
    item!(cart, "a", 5000, 1)
    march_coupon("WINDOW12", %{})

    at_end = assert_money(quote_via_query!(cart, %{as_of: ~U[2026-03-31 23:59:59Z], coupon_code: "WINDOW12"}))
    assert at_end.coupon_status == :applied
    assert at_end.coupon_discount_cents == 500

    after_end = assert_money(quote_via_query!(cart, %{as_of: ~U[2026-04-01 00:00:00Z], coupon_code: "WINDOW12"}))
    assert after_end.coupon_status == :expired
    assert after_end.coupon_discount_cents == 0
    assert after_end.total_cents == 5000
  end

  test "T13 redemption cap" do
    cart = cart!("t13", :us_or)
    item!(cart, "a", 5000, 1)

    march_coupon("CAP4", %{max_redemptions: 5, redemption_count: 4})
    march_coupon("CAP5", %{max_redemptions: 5, redemption_count: 5})
    march_coupon("CAPNIL", %{max_redemptions: nil, redemption_count: 9001})

    under = assert_money(quote_via_query!(cart, %{as_of: @march, coupon_code: "CAP4"}))
    assert under.coupon_status == :applied
    assert under.coupon_discount_cents == 500

    at_cap = assert_money(quote_via_query!(cart, %{as_of: @march, coupon_code: "CAP5"}))
    assert at_cap.coupon_status == :exhausted
    assert at_cap.coupon_discount_cents == 0

    unlimited = assert_money(quote_via_query!(cart, %{as_of: @march, coupon_code: "CAPNIL"}))
    assert unlimited.coupon_status == :applied
    assert unlimited.coupon_discount_cents == 500
  end

  test "T14 minimum subtotal" do
    below = cart!("t14-below", :us_or)
    item!(below, "a", 2999, 1)

    at_min = cart!("t14-at", :us_or)
    item!(at_min, "a", 3000, 1)

    march_coupon("MIN", %{min_subtotal_cents: 3000})

    q_below = assert_money(quote_via_query!(below, %{as_of: @march, coupon_code: "MIN"}))
    assert q_below.subtotal_cents == 2999
    assert q_below.coupon_status == :below_minimum
    assert q_below.coupon_discount_cents == 0

    q_at = assert_money(quote_via_query!(at_min, %{as_of: @march, coupon_code: "MIN"}))
    assert q_at.subtotal_cents == 3000
    assert q_at.coupon_status == :applied
    assert q_at.coupon_discount_cents == 300
  end

  test "T15 coupon discount rounding and cap" do
    odd_cart = cart!("t15-odd", :us_or)
    item!(odd_cart, "a", 999, 1)

    big_cart = cart!("t15-big", :us_or)
    item!(big_cart, "a", 10_000, 1)

    small_cart = cart!("t15-small", :us_or)
    item!(small_cart, "a", 400, 1)

    march_coupon("ODD", %{percent_off_bps: 1234, max_discount_cents: nil})
    march_coupon("CAP", %{percent_off_bps: 5000, max_discount_cents: 250})

    odd = assert_money(quote_via_query!(odd_cart, %{as_of: @march, coupon_code: "ODD"}))
    assert odd.coupon_status == :applied
    assert odd.coupon_discount_cents == 123

    capped = assert_money(quote_via_query!(big_cart, %{as_of: @march, coupon_code: "CAP"}))
    assert capped.coupon_status == :applied
    assert capped.coupon_discount_cents == 250

    uncapped = assert_money(quote_via_query!(small_cart, %{as_of: @march, coupon_code: "CAP"}))
    assert uncapped.coupon_status == :applied
    assert uncapped.coupon_discount_cents == 200
  end

  test "T16 rule precedence" do
    cart = cart!("t16", :us_or)
    item!(cart, "a", 5000, 1)

    coupon!(%{
      code: "WORST",
      percent_off_bps: 1000,
      starts_at: ~U[2026-01-01 00:00:00Z],
      ends_at: ~U[2026-01-31 23:59:59Z],
      max_redemptions: 1,
      redemption_count: 5,
      min_subtotal_cents: 1_000_000
    })

    coupon!(%{
      code: "EARLY",
      percent_off_bps: 1000,
      starts_at: ~U[2026-09-01 00:00:00Z],
      ends_at: ~U[2026-09-30 23:59:59Z],
      max_redemptions: 1,
      redemption_count: 5,
      min_subtotal_cents: 1_000_000
    })

    worst = assert_money(quote_via_query!(cart, %{as_of: @march, coupon_code: "WORST"}))
    assert worst.coupon_status == :expired

    early = assert_money(quote_via_query!(cart, %{as_of: @march, coupon_code: "EARLY"}))
    assert early.coupon_status == :not_yet_active
  end

  test "T17 us_ca half-away-from-zero rounding" do
    tie = cart!("t17-tie", :us_ca)
    item!(tie, "a", 200, 1)

    plain = cart!("t17-plain", :us_ca)
    item!(plain, "a", 1234, 3)

    q_tie = assert_money(quote_via_query!(tie, %{as_of: @march}))
    assert q_tie.discounted_subtotal_cents == 200
    assert q_tie.tax_cents == 19
    assert q_tie.total_cents == 219

    q_plain = assert_money(quote_via_query!(plain, %{as_of: @march}))
    assert q_plain.discounted_subtotal_cents == 3702
    assert q_plain.tax_cents == 342
    assert q_plain.total_cents == 4044
  end

  test "T18 eu_de half-to-even rounding" do
    even_tie = cart!("t18-even", :eu_de)
    item!(even_tie, "a", 1150, 1)

    odd_tie = cart!("t18-odd", :eu_de)
    item!(odd_tie, "a", 1050, 1)

    exact = cart!("t18-exact", :eu_de)
    item!(exact, "a", 2000, 1)

    q_even = assert_money(quote_via_query!(even_tie, %{as_of: @march}))
    assert q_even.tax_cents == 218
    assert q_even.total_cents == 1368

    q_odd = assert_money(quote_via_query!(odd_tie, %{as_of: @march}))
    assert q_odd.tax_cents == 200
    assert q_odd.total_cents == 1250

    q_exact = assert_money(quote_via_query!(exact, %{as_of: @march}))
    assert q_exact.tax_cents == 380
    assert q_exact.total_cents == 2380
  end

  test "T19 jp_13 truncation and us_or zero" do
    tie = cart!("t19-tie", :jp_13)
    item!(tie, "a", 1055, 1)

    frac = cart!("t19-frac", :jp_13)
    item!(frac, "a", 999, 1)

    free = cart!("t19-free", :us_or)
    item!(free, "a", 9999, 7)

    q_tie = assert_money(quote_via_query!(tie, %{as_of: @march}))
    assert q_tie.tax_cents == 105
    assert q_tie.total_cents == 1160

    q_frac = assert_money(quote_via_query!(frac, %{as_of: @march}))
    assert q_frac.tax_cents == 99
    assert q_frac.total_cents == 1098

    q_free = assert_money(quote_via_query!(free, %{as_of: @march}))
    assert q_free.tax_cents == 0
  end

  @batch [
    {"1", :us_ca, 200, 219},
    {"2", :eu_de, 1150, 1368},
    {"3", :jp_13, 1055, 1160},
    {"4", :us_or, 600, 600}
  ]

  defp seed_batch(prefix) do
    for {suffix, region, price, _total} <- @batch do
      cart = cart!(prefix <> suffix, region)
      item!(cart, "only", price, 1)
      cart
    end
  end

  defp batch_refs(prefix), do: Enum.map(@batch, fn {suffix, _, _, _} -> prefix <> suffix end)

  defp expected_totals(prefix) do
    Map.new(@batch, fn {suffix, _, _, total} -> {prefix <> suffix, total} end)
  end

  test "T20 batch load keeps per-record pairing" do
    seed_batch("b20-")
    refs = batch_refs("b20-")
    totals = expected_totals("b20-")

    carts =
      Cart
      |> Ash.Query.filter(reference in ^refs)
      |> Ash.Query.sort(reference: :desc)
      |> Ash.Query.load(pricing_quote: %{as_of: @march})
      |> Ash.read!()

    assert Enum.map(carts, & &1.reference) == Enum.sort(refs, :desc)

    for cart <- carts do
      q = assert_money(cart.pricing_quote)

      assert q.total_cents == Map.fetch!(totals, cart.reference),
             "cart #{cart.reference} got total #{q.total_cents}"

      assert q.item_count == 1
    end
  end

  test "T21 post-fetch load on unprepared structs" do
    seed_batch("b21-")
    refs = batch_refs("b21-")
    totals = expected_totals("b21-")

    carts =
      Cart
      |> Ash.Query.filter(reference in ^refs)
      |> Ash.Query.sort(reference: :asc)
      |> Ash.read!()

    loaded = Ash.load!(carts, pricing_quote: %{as_of: @march})

    assert Enum.map(loaded, & &1.reference) == Enum.sort(refs)

    for cart <- loaded do
      q = assert_money(cart.pricing_quote)
      assert q.total_cents == Map.fetch!(totals, cart.reference)
    end
  end

  test "T22 empty cart" do
    cart = cart!("t22", :eu_de)
    march_coupon("T22OK", %{min_subtotal_cents: 0})
    march_coupon("T22MIN", %{min_subtotal_cents: 1})

    plain = assert_money(quote_via_query!(cart, %{as_of: @march}))
    assert plain.coupon_status == :none

    for key <- @quote_keys -- [:coupon_status] do
      assert Map.fetch!(plain, key) == 0, "expected #{key} to be 0 on an empty cart"
    end

    ok = assert_money(quote_via_query!(cart, %{as_of: @march, coupon_code: "T22OK"}))
    assert ok.coupon_status == :applied

    for key <- @quote_keys -- [:coupon_status] do
      assert Map.fetch!(ok, key) == 0, "expected #{key} to be 0 on an empty cart"
    end

    below = assert_money(quote_via_query!(cart, %{as_of: @march, coupon_code: "T22MIN"}))
    assert below.coupon_status == :below_minimum
  end

  test "T23 arguments are honoured per load" do
    cart = cart!("t23", :us_or)
    item!(cart, "a", 10_000, 1)
    march_coupon("SEASON", %{percent_off_bps: 2000})

    fetched = Sales.get_cart!(cart.id)

    early =
      assert_money(
        Ash.load!(fetched, pricing_quote: %{as_of: ~U[2026-02-01 00:00:00Z], coupon_code: "SEASON"}).pricing_quote
      )

    assert early.coupon_status == :not_yet_active
    assert early.total_cents == 10_000

    active =
      assert_money(
        Ash.load!(fetched, pricing_quote: %{as_of: @march, coupon_code: "SEASON"}).pricing_quote
      )

    assert active.coupon_status == :applied
    assert active.total_cents == 8000

    none = assert_money(Ash.load!(fetched, pricing_quote: %{as_of: @march}).pricing_quote)
    assert none.coupon_status == :none
    assert none.total_cents == 10_000
  end

  test "T24 large exact values" do
    cart = cart!("t24", :eu_de)
    item!(cart, "a", 999_999_937, 3)
    item!(cart, "b", 123_456_789, 25)

    q = assert_money(quote_via_query!(cart, %{as_of: @march}))

    assert q.gross_subtotal_cents == 6_086_419_536
    assert q.subtotal_cents == 5_623_456_578
    assert q.tier_discount_cents == 462_962_958
    assert q.tax_cents == 1_068_456_750
    assert q.total_cents == 6_691_913_328
  end

  test "T25 write validation" do
    assert catch_error(Sales.create_cart!(%{reference: "t25", region: :mars}))

    assert Cart |> Ash.Query.filter(reference == "t25") |> Ash.read!() == []

    cart = cart!("t25-ok", :us_or)
    assert catch_error(item!(cart, "bad", 100, 0))

    assert CartItem |> Ash.Query.filter(cart_id == ^cart.id) |> Ash.read!() == []
  end

  test "T26 required quote argument" do
    cart = cart!("t26", :us_or)
    item!(cart, "a", 100, 1)
    fetched = Sales.get_cart!(cart.id)

    outcome =
      try do
        Ash.load(fetched, pricing_quote: %{})
      rescue
        error -> {:error, error}
      catch
        kind, reason -> {:error, {kind, reason}}
      end

    assert match?({:error, _}, outcome),
           "expected loading pricing_quote without as_of to fail, got: #{inspect(outcome)}"
  end
end
'''

def _run_suite() -> dict:
    os.makedirs(VERIFY_DIR, exist_ok=True)
    with open(HELPER_PATH, "w", encoding="utf-8") as handle:
        handle.write(TEST_HELPER_SRC)
    with open(SUITE_PATH, "w", encoding="utf-8") as handle:
        handle.write(SUITE_SRC)
    if os.path.exists(RESULTS_PATH):
        os.remove(RESULTS_PATH)

    env = dict(os.environ)
    env["MIX_ENV"] = "test"
    env["HEX_OFFLINE"] = "1"
    env.setdefault("MIX_HOME", "/opt/mix")
    env.setdefault("HEX_HOME", "/opt/hex")

    try:
        completed = subprocess.run(
            ["mix", "test", "--no-color", "--seed", "0", "test/verification/pricing_engine_test.exs"],
            cwd=PROJECT_DIR,
            env=env,
            capture_output=True,
            text=True,
            timeout=1800,
        )
        output = completed.stdout + "\n" + completed.stderr
    except subprocess.TimeoutExpired as exc:
        output = f"mix test timed out: {exc}"

    results = {}
    if os.path.exists(RESULTS_PATH):
        with open(RESULTS_PATH, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                results[record.get("name", "")] = record

    return {"results": results, "output": output}


@pytest.fixture(scope="session")
def suite_run():
    assert os.path.isdir(PROJECT_DIR), f"Project directory {PROJECT_DIR} is missing."
    assert shutil.which("mix") is not None, "mix was not found in PATH."
    return _run_suite()


def _check(suite, scenario: str):
    results = suite["results"]
    matches = [
        record
        for name, record in results.items()
        if name.startswith(f"test {scenario} ")
    ]
    if not matches:
        tail = suite["output"][-6000:]
        raise AssertionError(
            f"Scenario {scenario} did not run. The project or the verification suite failed "
            f"to compile or crashed.\n--- mix test output (tail) ---\n{tail}"
        )
    record = matches[0]
    status = record.get("status")
    assert status == "passed", (
        f"Scenario {scenario} ({record.get('name')}) reported status {status!r}.\n"
        f"{record.get('message', '')}"
    )


def test_t01_line_totals(suite_run):
    _check(suite_run, "T01")


def test_t02_tier_table(suite_run):
    _check(suite_run, "T02")


def test_t03_filter_and_sort_on_derived_item_fields(suite_run):
    _check(suite_run, "T03")


def test_t04_composed_line_discount(suite_run):
    _check(suite_run, "T04")


def test_t05_item_count_aggregate(suite_run):
    _check(suite_run, "T05")


def test_t06_quote_shape(suite_run):
    _check(suite_run, "T06")


def test_t07_no_coupon_zero_tax_region(suite_run):
    _check(suite_run, "T07")


def test_t08_mixed_tiers(suite_run):
    _check(suite_run, "T08")


def test_t09_nil_coupon_code(suite_run):
    _check(suite_run, "T09")


def test_t10_unknown_coupon_code(suite_run):
    _check(suite_run, "T10")


def test_t11_window_start_boundary(suite_run):
    _check(suite_run, "T11")


def test_t12_window_end_boundary(suite_run):
    _check(suite_run, "T12")


def test_t13_redemption_cap(suite_run):
    _check(suite_run, "T13")


def test_t14_minimum_subtotal(suite_run):
    _check(suite_run, "T14")


def test_t15_coupon_discount_rounding_and_cap(suite_run):
    _check(suite_run, "T15")


def test_t16_rule_precedence(suite_run):
    _check(suite_run, "T16")


def test_t17_us_ca_half_away_from_zero(suite_run):
    _check(suite_run, "T17")


def test_t18_eu_de_half_to_even(suite_run):
    _check(suite_run, "T18")


def test_t19_jp_13_truncation_and_us_or_zero(suite_run):
    _check(suite_run, "T19")


def test_t20_batch_load_pairing(suite_run):
    _check(suite_run, "T20")


def test_t21_post_fetch_load(suite_run):
    _check(suite_run, "T21")


def test_t22_empty_cart(suite_run):
    _check(suite_run, "T22")


def test_t23_arguments_honoured_per_load(suite_run):
    _check(suite_run, "T23")


def test_t24_large_exact_values(suite_run):
    _check(suite_run, "T24")


def test_t25_write_validation(suite_run):
    _check(suite_run, "T25")


def test_t26_required_quote_argument(suite_run):
    _check(suite_run, "T26")
