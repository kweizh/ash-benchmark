defmodule CartPricing.Sales.Cart do
  use Ash.Resource,
    domain: CartPricing.Sales,
    data_layer: Ash.DataLayer.Ets

  ets do
    private? false
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
      constraints [one_of: [:us_ca, :us_or, :eu_de, :jp_13]]
    end
  end

  relationships do
    has_many :items, CartPricing.Sales.CartItem do
      destination_attribute :cart_id
      public? true
    end
  end

  calculations do
    calculate :item_count, :integer, expr(count(items))

    calculate :pricing_quote, :map, {CartPricing.Sales.Calculations.CartQuote, []} do
      argument :coupon_code, :string do
        allow_nil? true
        default nil
      end

      argument :as_of, :utc_datetime do
        allow_nil? false
      end
    end
  end

  actions do
    defaults [:read, :destroy, update: :*]

    create :create do
      accept [:reference, :region]
      primary? true
    end
  end
end
