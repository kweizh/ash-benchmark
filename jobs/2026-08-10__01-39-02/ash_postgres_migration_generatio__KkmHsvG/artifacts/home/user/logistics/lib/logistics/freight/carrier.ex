defmodule Logistics.Freight.Carrier do
  use Ash.Resource,
    otp_app: :logistics,
    domain: Logistics.Freight,
    data_layer: AshPostgres.DataLayer

  resource do
    base_filter [is_nil: :retired_at]
  end

  postgres do
    table "carriers"
    repo Logistics.Repo

    custom_indexes do
      index [:code],
        unique: true,
        name: "carriers_unique_code_index",
        where: "retired_at IS NULL",
        message: "has already been taken",
        error_fields: [:code]
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
    has_many :shipments, Logistics.Freight.Shipment
  end

  actions do
    defaults [:read]

    create :create do
      accept [:code, :name, :retired_at]
    end

    update :update do
      accept [:code, :name, :retired_at]
    end

    destroy :destroy do
      primary? true
      require_atomic? false
      validate fn changeset, _context ->
        import Ecto.Query
        carrier_id = changeset.data.id
        case Logistics.Repo.all(from s in "shipments", where: s.carrier_id == type(^carrier_id, Ecto.UUID), select: s.id, limit: 1) do
          [] ->
            :ok
          _ ->
            {:error, Ash.Error.Changes.InvalidAttribute.exception(
              field: :shipments,
              message: "carrier still has shipments"
            )}
        end
      end
    end
  end
end
