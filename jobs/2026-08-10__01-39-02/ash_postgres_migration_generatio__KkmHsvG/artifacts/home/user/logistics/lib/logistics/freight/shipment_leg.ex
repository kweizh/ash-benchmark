defmodule Logistics.Freight.ShipmentLeg do
  use Ash.Resource,
    otp_app: :logistics,
    domain: Logistics.Freight,
    data_layer: AshPostgres.DataLayer

  postgres do
    table "shipment_legs"
    repo Logistics.Repo

    custom_indexes do
      index [:shipment_id, :sequence],
        unique: true,
        name: "shipment_legs_unique_leg_sequence_index",
        message: "has already been taken",
        error_fields: [:shipment_id]
    end

    check_constraints do
      check_constraint :sequence, "shipment_legs_sequence_positive",
        check: "sequence >= 1",
        message: "sequence must be at least 1"
    end

    references do
      reference :shipment, on_delete: :delete, on_update: :update, name: "shipment_legs_shipment_fkey", index?: true
      reference :warehouse, on_delete: :restrict, on_update: :update, name: "shipment_legs_warehouse_fkey", index?: true
    end
  end

  attributes do
    attribute :id, :uuid do
      primary_key? true
      default &Ash.UUID.generate/0
      allow_nil? false
      public? true
      writable? true
    end

    attribute :sequence, :integer do
      allow_nil? false
      public? true
    end
  end

  relationships do
    belongs_to :shipment, Logistics.Freight.Shipment do
      allow_nil? false
      public? true
      writable? true
      attribute_writable? true
      attribute_public? true
    end

    belongs_to :warehouse, Logistics.Freight.Warehouse do
      allow_nil? false
      public? true
      writable? true
      attribute_writable? true
      attribute_public? true
    end
  end

  actions do
    defaults [:read, :destroy]

    create :create do
      accept [:sequence, :shipment_id, :warehouse_id]
    end

    update :update do
      accept [:sequence, :shipment_id, :warehouse_id]
    end
  end
end
