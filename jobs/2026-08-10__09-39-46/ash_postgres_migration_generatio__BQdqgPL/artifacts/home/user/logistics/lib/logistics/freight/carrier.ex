defmodule Logistics.Freight.Carrier do
  use Ash.Resource,
    domain: Logistics.Freight,
    data_layer: AshPostgres.DataLayer

  postgres do
    table "carriers"
    repo Logistics.Repo

    identity_wheres_to_sql unique_code: "retired_at IS NULL"

    foreign_key_names shipments: "shipments_carrier_fkey"
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

  identities do
    identity :unique_code, [:code] do
      where expr(is_nil(retired_at))
      message "has already been taken"
    end
  end

  relationships do
    has_many :shipments, Logistics.Freight.Shipment do
      violation_message "carrier still has shipments"
    end
  end

  actions do
    default_accept :*
    defaults [:read, :create, :update, :destroy]
  end
end
