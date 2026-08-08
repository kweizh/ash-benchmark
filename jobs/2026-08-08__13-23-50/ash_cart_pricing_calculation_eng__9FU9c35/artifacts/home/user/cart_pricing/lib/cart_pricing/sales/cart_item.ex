defmodule CartPricing.Sales.CartItem do
  @moduledoc """
  A single line item within a `CartPricing.Sales.Cart`.

  Only raw facts (`sku`, `unit_price_cents`, `quantity`) are stored. The
  line total, the quantity-tier discount rate and the discounted line total
  are all derived at read time.
  """

  use Ash.Resource,
    domain: CartPricing.Sales,
    data_layer: Ash.DataLayer.Ets

  ets do
    private? true
  end

  actions do
    defaults [:read]

    create :create do
      accept [:sku, :unit_price_cents, :quantity, :cart_id]
    end
  end

  attributes do
    uuid_primary_key :id

    attribute :sku, :string do
      allow_nil? false
      public? true
    end

    attribute :unit_price_cents, :integer do
      allow_nil? false
      public? true
    end

    attribute :quantity, :integer do
      allow_nil? false
      public? true
      constraints min: 1
    end
  end

  relationships do
    belongs_to :cart, CartPricing.Sales.Cart do
      allow_nil? false
      public? true
      attribute_public? true
    end
  end

  calculations do
    calculate :line_total_cents, :integer, expr(unit_price_cents * quantity) do
      public? true
    end

    calculate :tier_discount_bps,
              :integer,
              expr(
                cond do
                  quantity >= 25 -> 1500
                  quantity >= 10 -> 1000
                  quantity >= 5 -> 500
                  true -> 0
                end
              ) do
      public? true
    end

    calculate :discounted_line_total_cents,
              :integer,
              CartPricing.Sales.Calculations.DiscountedLineTotal do
      public? true
    end
  end
end
