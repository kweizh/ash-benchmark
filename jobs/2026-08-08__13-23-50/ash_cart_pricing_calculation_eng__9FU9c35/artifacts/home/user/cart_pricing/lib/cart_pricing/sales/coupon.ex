defmodule CartPricing.Sales.Coupon do
  @moduledoc """
  A coupon that may apply a percentage discount to a cart's subtotal.

  Coupons store only raw facts - the actual discount amount for a given
  cart is always computed at read time (see
  `CartPricing.Sales.Calculations.CartQuote`).
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
      accept [
        :code,
        :percent_off_bps,
        :starts_at,
        :ends_at,
        :max_redemptions,
        :redemption_count,
        :min_subtotal_cents,
        :max_discount_cents
      ]
    end
  end

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
end
