defmodule Logistics.Freight.Shipment do
  use Ash.Resource,
    otp_app: :logistics,
    domain: Logistics.Freight,
    data_layer: AshPostgres.DataLayer

  postgres do
    table "shipments"
    repo Logistics.Repo

    migration_defaults booked_at: "fragment(\"now()\")"

    custom_indexes do
      index [:reference],
        unique: true,
        name: "shipments_unique_reference_index",
        message: "has already been taken",
        error_fields: [:reference]
    end

    check_constraints do
      check_constraint :declared_value_cents, "shipments_declared_value_cents_non_negative",
        check: "declared_value_cents >= 0",
        message: "declared value must not be negative"
    end

    references do
      reference :carrier, on_delete: :restrict, on_update: :update, name: "shipments_carrier_fkey", index?: true
      reference :origin_warehouse, on_delete: :nilify, on_update: :update, name: "shipments_origin_warehouse_fkey"
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

    attribute :reference, :string do
      allow_nil? false
      public? true
    end

    attribute :status, :atom do
      allow_nil? false
      constraints [one_of: [:draft, :booked, :in_transit, :delivered, :cancelled]]
      default :draft
      public? true
    end

    attribute :declared_value_cents, :integer do
      allow_nil? false
      default 0
      public? true
    end

    attribute :scheduled_for, :utc_datetime do
      allow_nil? true
      public? true
    end

    attribute :booked_at, :utc_datetime_usec do
      allow_nil? true
      default &DateTime.utc_now/0
      public? true
    end
  end

  relationships do
    belongs_to :carrier, Logistics.Freight.Carrier do
      allow_nil? false
      public? true
      writable? true
      attribute_writable? true
      attribute_public? true
    end

    belongs_to :origin_warehouse, Logistics.Freight.Warehouse do
      allow_nil? true
      public? true
      writable? true
      attribute_writable? true
      attribute_public? true
    end

    has_many :parcels, Logistics.Freight.Parcel
    has_many :legs, Logistics.Freight.ShipmentLeg
  end

  aggregates do
    count :parcel_count, :parcels do
      public? true
    end

    sum :total_weight_grams, :parcels, :weight_grams do
      default 0
      public? true
    end
  end

  calculations do
    calculate :heavy?, :boolean, expr(total_weight_grams > 5000) do
      public? true
    end
  end

  actions do
    defaults [:read, :destroy]

    create :create do
      accept [:reference, :status, :declared_value_cents, :scheduled_for, :booked_at, :carrier_id, :origin_warehouse_id]
    end

    update :update do
      accept [:reference, :status, :declared_value_cents, :scheduled_for, :booked_at, :carrier_id, :origin_warehouse_id]
    end

    create :intake do
      accept [:reference, :declared_value_cents, :scheduled_for, :carrier_id, :origin_warehouse_id]
      argument :parcels, {:array, :map} do
        allow_nil? false
      end

      change fn changeset, _context ->
        Ash.Changeset.after_action(changeset, fn changeset, shipment ->
          parcels_args = Ash.Changeset.get_argument(changeset, :parcels)

          results =
            Enum.reduce_while(parcels_args, {:ok, []}, fn parcel_map, {:ok, acc} ->
              tracking_code = Map.get(parcel_map, :tracking_code) || Map.get(parcel_map, "tracking_code")
              weight_grams = Map.get(parcel_map, :weight_grams) || Map.get(parcel_map, "weight_grams")
              fragile = Map.get(parcel_map, :fragile) || Map.get(parcel_map, "fragile") || false

              parcel_changeset =
                Logistics.Freight.Parcel
                |> Ash.Changeset.for_create(:create, %{
                  tracking_code: tracking_code,
                  weight_grams: weight_grams,
                  fragile: fragile,
                  shipment_id: shipment.id
                })

              case Ash.create(parcel_changeset) do
                {:ok, parcel} ->
                  {:cont, {:ok, [parcel | acc]}}

                {:error, error} ->
                  {:halt, {:error, error}}
              end
            end)

          case results do
            {:ok, _parcels} ->
              {:ok, shipment}

            {:error, error} ->
              {:error, error}
          end
        end)
      end
    end
  end
end
