defmodule Catering.Orders.Modifier do
  use Ash.Resource,
    otp_app: :catering,
    domain: Catering.Orders,
    data_layer: Ash.DataLayer.Ets

  ets do
    private? true
  end

  attributes do
    uuid_primary_key :id
    attribute :label, :string, allow_nil?: false, public?: true
    attribute :surcharge_cents, :integer, allow_nil?: false, default: 0, public?: true
    attribute :position, :integer, allow_nil?: false, default: 0, public?: true
  end

  relationships do
    belongs_to :line_item, Catering.Orders.LineItem do
      public? true
      attribute_writable? true
    end
  end

  actions do
    defaults [:read, :destroy]
    default_accept [:label, :surcharge_cents, :position]

    create :add do
      primary? true
      accept [:label, :surcharge_cents, :position]
    end

    update :revise do
      primary? true
      accept [:label, :surcharge_cents, :position]
    end
  end

  validations do
    validate compare(:surcharge_cents, greater_than_or_equal_to: 0),
      message: "must not be negative"
  end
end
