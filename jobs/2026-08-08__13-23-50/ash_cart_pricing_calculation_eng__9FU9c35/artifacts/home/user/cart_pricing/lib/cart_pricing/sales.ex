defmodule CartPricing.Sales do
  @moduledoc """
  The Sales domain owns the cart pricing resources: `Cart`, `CartItem` and
  `Coupon`.

  No monetary figure is ever stored on these resources - every subtotal,
  discount, tax and total is derived at read time from raw facts (unit
  prices, quantities, coupon rules) plus load-time inputs (a coupon code and
  a point in time).
  """

  use Ash.Domain

  resources do
    resource CartPricing.Sales.Cart do
      define :create_cart, action: :create
      define :get_cart, action: :read, get_by: [:id]
    end

    resource CartPricing.Sales.CartItem do
      define :create_cart_item, action: :create
    end

    resource CartPricing.Sales.Coupon do
      define :create_coupon, action: :create
    end
  end
end
