defmodule Logistics.Freight.Warehouse do
  use Ash.Resource,
    otp_app: :logistics,
    domain: Logistics.Freight,
    data_layer: AshPostgres.DataLayer

  import Ash.Expr

  postgres do
    table "warehouses"
    repo Logistics.Repo

    identity_wheres_to_sql unique_active_code: "decommissioned = false"

    foreign_key_names [
      {:legs, "shipment_legs_warehouse_fkey", "warehouse still has shipment legs"}
    ]

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

  relationships do
    has_many :legs, Logistics.Freight.ShipmentLeg do
      public? true
    end
  end

  identities do
    identity :unique_active_code, [:code], where: expr(decommissioned == false)
  end

  actions do
    defaults [:read, :destroy, create: :*, update: :*]
  end
end
