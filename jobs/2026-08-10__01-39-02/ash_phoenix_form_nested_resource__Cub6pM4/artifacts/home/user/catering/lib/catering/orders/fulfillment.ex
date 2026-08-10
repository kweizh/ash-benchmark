defmodule Catering.Orders.CourierDrop do
  use Ash.Resource, data_layer: :embedded

  attributes do
    attribute :kind, :string, public?: true
    attribute :street, :string, allow_nil?: false, public?: true
    attribute :postcode, :string, allow_nil?: false, public?: true
  end

  actions do
    defaults [:read, :destroy, create: :*, update: :*]
  end
end

defmodule Catering.Orders.CounterPickup do
  use Ash.Resource, data_layer: :embedded

  attributes do
    attribute :kind, :string, public?: true
    attribute :counter, :string, allow_nil?: false, public?: true
  end

  actions do
    defaults [:read, :destroy, create: :*, update: :*]
  end
end

defmodule Catering.Orders.Fulfillment do
  use Ash.Type.NewType,
    subtype_of: :union,
    constraints: [
      types: [
        courier: [
          type: Catering.Orders.CourierDrop,
          tag: :kind,
          tag_value: "courier"
        ],
        pickup: [
          type: Catering.Orders.CounterPickup,
          tag: :kind,
          tag_value: "pickup"
        ]
      ]
    ]
end
