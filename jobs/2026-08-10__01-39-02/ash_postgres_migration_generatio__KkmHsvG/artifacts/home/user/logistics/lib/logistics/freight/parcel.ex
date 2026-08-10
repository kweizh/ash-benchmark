defmodule Logistics.Freight.Parcel do
  use Ash.Resource,
    otp_app: :logistics,
    domain: Logistics.Freight,
    data_layer: AshPostgres.DataLayer

  postgres do
    table "parcels"
    repo Logistics.Repo

    custom_indexes do
      index [:tracking_code],
        unique: true,
        name: "parcels_unique_tracking_code_index",
        message: "has already been taken",
        error_fields: [:tracking_code]

      index [:shipment_id],
        unique: true,
        name: "parcels_single_fragile_per_shipment_index",
        where: "fragile = true",
        message: "has already been taken",
        error_fields: [:shipment_id]
    end

    check_constraints do
      check_constraint :weight_grams, "parcels_weight_grams_positive",
        check: "weight_grams > 0",
        message: "weight must be positive"
    end

    references do
      reference :shipment, on_delete: :delete, on_update: :update, name: "parcels_shipment_fkey", index?: true
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
      writable? true
      attribute_writable? true
      attribute_public? true
    end
  end

  actions do
    defaults [:read, :destroy]

    create :create do
      accept [:tracking_code, :weight_grams, :fragile, :shipment_id]
    end

    update :update do
      accept [:tracking_code, :weight_grams, :fragile, :shipment_id]
    end
  end
end
