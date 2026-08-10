defmodule Logistics.Freight.ShipmentLeg do
  use Ash.Resource,
    domain: Logistics.Freight,
    data_layer: AshPostgres.DataLayer

  postgres do
    table "shipment_legs"
    repo Logistics.Repo

    references do
      reference :shipment,
        on_delete: :delete,
        on_update: :update,
        name: "shipment_legs_shipment_fkey",
        index?: true

      reference :warehouse,
        on_delete: :restrict,
        on_update: :update,
        name: "shipment_legs_warehouse_fkey",
        index?: true
    end

    check_constraints do
      check_constraint :sequence, "shipment_legs_sequence_positive",
        check: "sequence >= 1",
        message: "sequence must be at least 1"
    end
  end

  attributes do
    uuid_primary_key :id

    attribute :sequence, :integer do
      allow_nil? false
      public? true
    end
  end

  identities do
    identity :unique_leg_sequence, [:shipment_id, :sequence] do
      message "has already been taken"
    end
  end

  relationships do
    belongs_to :shipment, Logistics.Freight.Shipment do
      allow_nil? false
      public? true
    end

    belongs_to :warehouse, Logistics.Freight.Warehouse do
      allow_nil? false
      public? true
    end
  end

  actions do
    default_accept :*
    defaults [:read, :create, :update, :destroy]
  end
end
