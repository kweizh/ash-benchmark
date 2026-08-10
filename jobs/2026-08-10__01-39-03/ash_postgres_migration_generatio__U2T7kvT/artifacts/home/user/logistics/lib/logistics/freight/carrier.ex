defmodule Logistics.Freight.Carrier do
  use Ash.Resource,
    otp_app: :logistics,
    domain: Logistics.Freight,
    data_layer: AshPostgres.DataLayer

  import Ash.Expr

  postgres do
    table "carriers"
    repo Logistics.Repo

    identity_wheres_to_sql unique_code: "retired_at IS NULL"

    foreign_key_names [
      {:shipments, "shipments_carrier_fkey", "carrier still has shipments"}
    ]
  end

  attributes do
    uuid_primary_key :id

    attribute :code, :ci_string do
      allow_nil? false
      public? true
    end

    attribute :name, :string do
      allow_nil? false
      public? true
    end

    attribute :retired_at, :utc_datetime_usec do
      allow_nil? true
      public? true
    end
  end

  relationships do
    has_many :shipments, Logistics.Freight.Shipment do
      public? true
    end
  end

  identities do
    identity :unique_code, [:code], where: expr(is_nil(retired_at))
  end

  preparations do
    prepare build(filter: expr(is_nil(retired_at)))
  end

  actions do
    defaults [:read, :destroy, create: :*, update: :*]
  end
end
