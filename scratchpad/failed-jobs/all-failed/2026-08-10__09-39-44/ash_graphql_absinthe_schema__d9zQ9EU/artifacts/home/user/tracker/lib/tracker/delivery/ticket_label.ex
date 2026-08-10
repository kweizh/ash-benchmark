defmodule Tracker.Delivery.TicketLabel do
  @moduledoc false
  use Ash.Resource,
    otp_app: :tracker,
    domain: Tracker.Delivery,
    data_layer: Ash.DataLayer.Ets

  ets do
    private? true
  end

  attributes do
    uuid_primary_key :id
  end

  actions do
    defaults [:read, :destroy, create: :*, update: :*]
  end

  relationships do
    belongs_to :ticket, Tracker.Delivery.Ticket do
      allow_nil? false
      attribute_writable? true
    end

    belongs_to :label, Tracker.Delivery.Label do
      allow_nil? false
      attribute_writable? true
    end
  end
end
