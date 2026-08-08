defmodule CartPricing.Sales.CartItem do
  use Ash.Resource,
    domain: CartPricing.Sales,
    data_layer: Ash.DataLayer.Ets

  ets do
    private? false
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
      constraints [min: 1]
    end
  end

  relationships do
    belongs_to :cart, CartPricing.Sales.Cart do
      allow_nil? false
      public? true
    end
  end

  calculations do
    calculate :line_total_cents, :integer, expr(unit_price_cents * quantity)

    calculate :tier_discount_bps, :integer, expr(
      if quantity >= 25 do
        1500
      else
        if quantity >= 10 do
          1000
        else
          if quantity >= 5 do
            500
          else
            0
          end
        end
      end
    )

    calculate :discounted_line_total_cents, :integer, {CartPricing.Sales.Calculations.DiscountedLineTotal, []}
  end

  actions do
    defaults [:read, :destroy, update: :*]

    create :create do
      accept [:sku, :unit_price_cents, :quantity, :cart_id]
      primary? true
    end
  end
end
