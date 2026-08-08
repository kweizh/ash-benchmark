defmodule CartPricing.Sales do
  use Ash.Domain

  resources do
    resource CartPricing.Sales.Cart
    resource CartPricing.Sales.CartItem
    resource CartPricing.Sales.Coupon
  end

  def create_cart!(attrs) do
    CartPricing.Sales.Cart
    |> Ash.Changeset.for_create(:create, attrs)
    |> Ash.create!()
  end

  def create_cart_item!(attrs) do
    CartPricing.Sales.CartItem
    |> Ash.Changeset.for_create(:create, attrs)
    |> Ash.create!()
  end

  def create_coupon!(attrs) do
    CartPricing.Sales.Coupon
    |> Ash.Changeset.for_create(:create, attrs)
    |> Ash.create!()
  end

  def get_cart!(id) do
    Ash.get!(CartPricing.Sales.Cart, id)
  end
end
