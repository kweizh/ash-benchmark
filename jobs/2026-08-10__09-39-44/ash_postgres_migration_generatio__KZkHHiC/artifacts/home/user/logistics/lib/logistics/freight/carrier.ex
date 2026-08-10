defmodule Logistics.Freight.Carrier do
  use Ash.Resource,
    domain: Logistics.Freight,
    data_layer: AshPostgres.DataLayer

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
    identity :unique_code, [:code]
  end

  actions do
    default_accept :*
    defaults [:read, :create, :update, :destroy]
  end

  postgres do
    table "carriers"
    repo Logistics.Repo

    base_filter_sql "retired_at IS NULL"

    foreign_key_names [
      {:shipments, "shipments_carrier_fkey", "carrier still has shipments"}
    ]
  end

  resource do
    base_filter expr(is_nil(retired_at))
  end
end
