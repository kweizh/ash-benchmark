defmodule Tracker.Delivery.Label do
  @moduledoc false
  use Ash.Resource,
    otp_app: :tracker,
    domain: Tracker.Delivery,
    data_layer: Ash.DataLayer.Ets,
    extensions: [AshGraphql.Resource]

  ets do
    private? true
  end

  graphql do
    type :label
    sortable_fields [:name]
    filterable_fields [:name]

    queries do
      list :labels, :read
    end
  end

  attributes do
    uuid_primary_key :id
    attribute :name, :string, allow_nil?: false, public?: true
    attribute :colour, :string, public?: true
  end

  actions do
    defaults [:read, :destroy, create: :*, update: :*]
  end

  relationships do
    many_to_many :tickets, Tracker.Delivery.Ticket do
      through Tracker.Delivery.TicketLabel
      source_attribute_on_join_resource :label_id
      destination_attribute_on_join_resource :ticket_id
      public? true
    end
  end
end
