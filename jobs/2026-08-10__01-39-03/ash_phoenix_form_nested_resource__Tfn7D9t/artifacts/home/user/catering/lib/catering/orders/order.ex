defmodule Catering.Orders.Order do
  use Ash.Resource,
    otp_app: :catering,
    domain: Catering.Orders,
    data_layer: Ash.DataLayer.Ets

  ets do
    private? true
  end

  attributes do
    uuid_primary_key :id
    attribute :reference, :string, allow_nil?: false, public?: true
    attribute :note, :string, public?: true

    attribute :delivery_windows, {:array, Catering.Orders.DeliveryWindow} do
      public? true
      default []
    end

    attribute :fulfillment, Catering.Orders.Fulfillment do
      public? true
    end
  end

  relationships do
    belongs_to :customer, Catering.Orders.Customer do
      public? true
      attribute_writable? true
    end

    has_many :line_items, Catering.Orders.LineItem do
      public? true
    end
  end

  actions do
    defaults [:read, :destroy]
    default_accept [:reference, :note, :delivery_windows, :fulfillment]

    create :place do
      accept [:reference, :note, :delivery_windows, :fulfillment]
      argument :customer, :map
      argument :line_items, {:array, :map}

      change manage_relationship(:customer,
               on_lookup: :relate,
               on_no_match: :create,
               on_match: :ignore
             )

      change manage_relationship(:line_items, type: :direct_control, order_is_key: :position)
    end

    update :revise do
      require_atomic? false
      accept [:reference, :note, :delivery_windows, :fulfillment]
      argument :line_items, {:array, :map}

      change manage_relationship(:line_items, type: :direct_control, order_is_key: :position)
    end
  end
end
