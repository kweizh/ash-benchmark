defmodule Logistics.Freight.Parcel do
  use Ash.Resource,
    otp_app: :logistics,
    domain: Logistics.Freight,
    data_layer: AshPostgres.DataLayer

  import Ash.Expr

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

  relationships do
    belongs_to :shipment, Logistics.Freight.Shipment do
      allow_nil? false
      public? true
    end
  end

  identities do
    identity :unique_tracking_code, [:tracking_code]
    identity :single_fragile_per_shipment, [:shipment_id], where: expr(fragile == true)
  end

  actions do
    defaults [:read, :destroy, create: :*, update: :*]
  end
end
