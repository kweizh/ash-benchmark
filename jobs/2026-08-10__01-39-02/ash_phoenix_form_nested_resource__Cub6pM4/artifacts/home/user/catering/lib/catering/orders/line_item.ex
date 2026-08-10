defmodule Catering.Orders.LineItem do
  use Ash.Resource,
    otp_app: :catering,
    domain: Catering.Orders,
    data_layer: Ash.DataLayer.Ets

  ets do
    private? true
  end

  attributes do
    uuid_primary_key :id
    attribute :dish, :string, allow_nil?: false, public?: true
    attribute :quantity, :integer, allow_nil?: false, default: 1, public?: true
    attribute :position, :integer, allow_nil?: false, default: 0, public?: true
  end

  relationships do
    belongs_to :order, Catering.Orders.Order do
      public? true
      attribute_writable? true
    end

    has_many :modifiers, Catering.Orders.Modifier do
      public? true
    end
  end

  actions do
    defaults [:read, :destroy]
    default_accept [:dish, :quantity, :position]

    create :add do
      primary? true
      accept [:dish, :quantity, :position]
      argument :modifiers, {:array, :map}
      change manage_relationship(:modifiers, type: :direct_control, order_is_key: :position)
    end

    update :revise do
      primary? true
      require_atomic? false
      accept [:dish, :quantity, :position]
      argument :modifiers, {:array, :map}
      change manage_relationship(:modifiers, type: :direct_control, order_is_key: :position)
    end
  end

  validations do
    validate compare(:quantity, greater_than: 0), message: "must be positive"
  end
end
