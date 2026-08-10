defmodule Logistics.Freight.Parcel do
  use Ash.Resource,
    domain: Logistics.Freight,
    data_layer: AshPostgres.DataLayer

  postgres do
    table "parcels"
    repo Logistics.Repo

    identity_wheres_to_sql single_fragile_per_shipment: "fragile = true"

    references do
      reference :shipment,
        on_delete: :delete,
        on_update: :update,
        name: "parcels_shipment_fkey",
        index?: true
    end

    check_constraints do
      check_constraint :weight_grams, "parcels_weight_grams_positive",
        check: "weight_grams > 0",
        message: "weight must be positive"
    end
  end

  attributes do
    uuid_primary_key :id

    attribute :tracking_code, :string do
      allow_nil? false
      public? true
    end

    attribute :weight_grams, :integer do
      allow_nil? false
      public? true
    end

    attribute :fragile, :boolean do
      allow_nil? false
      default false
      public? true
    end
  end

  identities do
    identity :unique_tracking_code, [:tracking_code] do
      message "has already been taken"
    end

    identity :single_fragile_per_shipment, [:shipment_id] do
      where expr(fragile == true)
      message "has already been taken"
    end
  end

  relationships do
    belongs_to :shipment, Logistics.Freight.Shipment do
      allow_nil? false
      public? true
    end
  end

  actions do
    default_accept :*
    defaults [:read, :create, :update, :destroy]
  end
end
