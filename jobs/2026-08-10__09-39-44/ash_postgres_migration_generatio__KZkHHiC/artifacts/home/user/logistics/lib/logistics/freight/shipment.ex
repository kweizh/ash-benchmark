defmodule Logistics.Freight.Shipment do
  use Ash.Resource,
    domain: Logistics.Freight,
    data_layer: AshPostgres.DataLayer

  attributes do
    uuid_primary_key :id

    attribute :reference, :string do
      allow_nil? false
      public? true
    end

    attribute :status, :atom do
      allow_nil? false
      public? true
      default :draft
      constraints one_of: [:draft, :booked, :in_transit, :delivered, :cancelled]
    end

    attribute :declared_value_cents, :integer do
      allow_nil? false
      public? true
      default 0
    end

    attribute :scheduled_for, :utc_datetime do
      allow_nil? true
      public? true
    end

    attribute :booked_at, :utc_datetime_usec do
      allow_nil? true
      public? true
      default &DateTime.utc_now/0
    end
  end

  relationships do
    belongs_to :carrier, Logistics.Freight.Carrier do
      allow_nil? false
      attribute_public? true
      public? true
    end

    belongs_to :origin_warehouse, Logistics.Freight.Warehouse do
      allow_nil? true
      attribute_public? true
      public? true
    end

    has_many :parcels, Logistics.Freight.Parcel do
      public? true
    end

    has_many :legs, Logistics.Freight.ShipmentLeg do
      public? true
    end
  end

  identities do
    identity :unique_reference, [:reference]
  end

  aggregates do
    count :parcel_count, :parcels
    sum :total_weight_grams, :parcels, :weight_grams
  end

  calculations do
    calculate :heavy?, :boolean, expr((total_weight_grams || 0) > 5000)
  end

  actions do
    default_accept :*
    defaults [:read, :create, :update, :destroy]

    create :intake do
      accept [:reference, :declared_value_cents, :scheduled_for, :carrier_id, :origin_warehouse_id]

      argument :parcels, {:array, :map} do
        allow_nil? false
      end

      change manage_relationship(:parcels, type: :create)
    end
  end

  postgres do
    table "shipments"
    repo Logistics.Repo

    migration_types [scheduled_for: :timestamptz]

    migration_defaults [
      booked_at: ~S[fragment("now()")]
    ]

    references do
      reference :carrier,
        on_delete: :restrict,
        on_update: :update,
        name: "shipments_carrier_fkey"

      reference :origin_warehouse,
        on_delete: :nilify,
        on_update: :update,
        name: "shipments_origin_warehouse_fkey"
    end

    custom_indexes do
      index [:carrier_id], name: "shipments_carrier_id_index"
    end

    check_constraints do
      check_constraint :declared_value_cents, "shipments_declared_value_cents_non_negative",
        check: "declared_value_cents >= 0",
        message: "declared value must not be negative"
    end
  end
end
