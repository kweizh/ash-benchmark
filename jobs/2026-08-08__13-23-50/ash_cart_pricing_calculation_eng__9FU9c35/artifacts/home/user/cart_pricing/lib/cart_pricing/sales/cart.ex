defmodule CartPricing.Sales.Cart do
  @moduledoc """
  A shopping cart.

  Carts hold only raw facts (`reference`, `region`) and their line items.
  Every money figure related to the cart is derived at read time - see
  `pricing_quote/2` (backed by `CartPricing.Sales.Calculations.CartQuote`).
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
      accept [:reference, :region]
    end
  end

  attributes do
    uuid_primary_key :id

    attribute :reference, :string do
      allow_nil? false
      public? true
    end

    attribute :region, :atom do
      allow_nil? false
      public? true
      constraints one_of: [:us_ca, :us_or, :eu_de, :jp_13]
    end
  end

  relationships do
    has_many :items, CartPricing.Sales.CartItem do
      public? true
    end
  end

  aggregates do
    count :item_count, :items do
      public? true
    end
  end

  calculations do
    calculate :pricing_quote, :map, CartPricing.Sales.Calculations.CartQuote do
      public? true

      argument :coupon_code, :string do
        allow_nil? true
        default nil
      end

      argument :as_of, :utc_datetime do
        allow_nil? false
      end
    end
  end
end
