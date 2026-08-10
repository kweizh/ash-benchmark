defmodule Catering.Orders do
  use Ash.Domain, otp_app: :catering

  resources do
    resource Catering.Orders.Customer
    resource Catering.Orders.Order
    resource Catering.Orders.LineItem
    resource Catering.Orders.Modifier
  end
end
