defmodule Catering.Orders.DeliveryWindow do
  use Ash.Resource,
    data_layer: :embedded

  attributes do
    uuid_primary_key :id, writable?: true
    attribute :label, :string, allow_nil?: false, public?: true
    attribute :starts_at_minute, :integer, allow_nil?: false, public?: true
    attribute :ends_at_minute, :integer, allow_nil?: false, public?: true
  end

  actions do
    defaults [:read, :destroy, create: :*, update: :*]
  end

  validations do
    validate compare(:ends_at_minute, greater_than: :starts_at_minute),
      message: "must be after the start"
  end
end
