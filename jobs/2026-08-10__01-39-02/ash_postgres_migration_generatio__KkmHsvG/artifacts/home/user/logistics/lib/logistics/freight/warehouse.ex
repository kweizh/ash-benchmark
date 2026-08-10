defmodule Logistics.Freight.Warehouse do
  use Ash.Resource,
    otp_app: :logistics,
    domain: Logistics.Freight,
    data_layer: AshPostgres.DataLayer

  postgres do
    table "warehouses"
    repo Logistics.Repo

    custom_indexes do
      index [:code],
        unique: true,
        name: "warehouses_unique_active_code_index",
        where: "decommissioned = false",
        message: "has already been taken",
        error_fields: [:code]
    end

    check_constraints do
      check_constraint :capacity_parcels, "warehouses_capacity_parcels_non_negative",
        check: "capacity_parcels >= 0",
        message: "capacity must not be negative"
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
    has_many :legs, Logistics.Freight.ShipmentLeg
  end

  actions do
    defaults [:read]

    create :create do
      accept [:code, :name, :region, :capacity_parcels, :decommissioned]
    end

    update :update do
      accept [:code, :name, :region, :capacity_parcels, :decommissioned]
    end

    destroy :destroy do
      primary? true
      require_atomic? false
      validate fn changeset, _context ->
        import Ecto.Query
        warehouse_id = changeset.data.id
        case Logistics.Repo.all(from sl in "shipment_legs", where: sl.warehouse_id == type(^warehouse_id, Ecto.UUID), select: sl.id, limit: 1) do
          [] ->
            :ok
          _ ->
            {:error, Ash.Error.Changes.InvalidAttribute.exception(
              field: :legs,
              message: "warehouse still has shipment legs"
            )}
        end
      end
    end
  end
end
