defmodule CartPricing.Sales.Coupon do
  use Ash.Resource,
    domain: CartPricing.Sales,
    data_layer: Ash.DataLayer.Ets

  attributes do
    uuid_primary_key :id

    attribute :code, :string do
      allow_nil? false
      public? true
    end

    attribute :percent_off_bps, :integer do
      allow_nil? false
      public? true
    end

    attribute :starts_at, :utc_datetime do
      allow_nil? false
      public? true
    end

    attribute :ends_at, :utc_datetime do
      allow_nil? false
      public? true
    end

    attribute :max_redemptions, :integer do
      allow_nil? true
      public? true
    end

    attribute :redemption_count, :integer do
      allow_nil? false
      default 0
      public? true
    end

    attribute :min_subtotal_cents, :integer do
      allow_nil? false
      default 0
      public? true
    end

    attribute :max_discount_cents, :integer do
      allow_nil? true
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
