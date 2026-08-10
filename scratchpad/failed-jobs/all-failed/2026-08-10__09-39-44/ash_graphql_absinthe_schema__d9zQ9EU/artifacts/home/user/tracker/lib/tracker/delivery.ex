defmodule Tracker.Delivery do
  @moduledoc false
  use Ash.Domain, otp_app: :tracker

  resources do
    resource Tracker.Delivery.User
    resource Tracker.Delivery.Project
    resource Tracker.Delivery.Ticket
    resource Tracker.Delivery.Label
    resource Tracker.Delivery.TicketLabel
  end
end
