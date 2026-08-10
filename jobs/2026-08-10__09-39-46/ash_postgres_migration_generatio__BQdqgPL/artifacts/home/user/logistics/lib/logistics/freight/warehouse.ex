defmodule Logistics.Freight.Warehouse do
  use Ash.Resource,
    domain: Logistics.Freight,
    data_layer: AshPostgres.DataLayer

  postgres do
    table "warehouses"
    repo Logistics.Repo

    identity_wheres_to_sql unique_active_code: "decommissioned = false"

    foreign_key_names legs: "shipment_legs_warehouse_fkey"

    check_constraints do
      check_constraint :capacity_parcels, "warehouses_capacity_parcels_non_negative",
        check: "capacity_parcels >= 0",
        message: "capacity must not be negative"
    end
  end

  attributes do
    uuid_primary_key :id

    attribute :code, :string do
      allow_nil? false
      public? true
    end

    attribute :name, :string do
      allow_nil? false
      public? true
    end

    attribute :region, :string do
      allow_nil? false
      public? true
    end

    attribute :capacity_parcels, :integer do
      allow_nil? false
      default 0
      public? true
    end

    attribute :decommissioned, :boolean do
      allow_nil? false
      default false
      public? true
    end
  end

  identities do
    identity :unique_active_code, [:code] do
      where expr(decommissioned == false)
      message "has already been taken"
    end
  end

  relationships do
    has_many :legs, Logistics.Freight.ShipmentLeg do
      violation_message "warehouse still has shipment legs"
    end
  end

  actions do
    default_accept :*
    defaults [:read, :create, :update, :destroy]
  end
end
