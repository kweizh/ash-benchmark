defmodule CartPricing.Sales.Cart do
  use Ash.Resource,
    domain: CartPricing.Sales,
    data_layer: Ash.DataLayer.Ets

  attributes do
    uuid_primary_key :id

    attribute :reference, :string do
      allow_nil? false
      public? true
    end

    attribute :region, :atom do
      allow_nil? false
      constraints one_of: [:us_ca, :us_or, :eu_de, :jp_13]
      public? true
    end
  end

  relationships do
    has_many :items, CartPricing.Sales.CartItem, public?: true
  end

  aggregates do
    count :item_count, :items, public?: true
  end

  calculations do
    calculate :pricing_quote, :map, CartPricing.Sales.Calculations.CartQuote do
      argument :coupon_code, :string do
        allow_nil? true
        default nil
      end

      argument :as_of, :utc_datetime do
        allow_nil? false
      end

      public? true
    end
  end

  actions do
    defaults [:read, :destroy]

    create :create do
      accept :*
    end

    update :update do
      accept :*
    end
  end
end
