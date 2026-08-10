defmodule Ingest.Pipeline.Reading do
  use Ash.Resource,
    otp_app: :ingest,
    domain: Ingest.Pipeline,
    data_layer: Ash.DataLayer.Ets

  require Ash.Query

  ets do
    private? true
  end

  attributes do
    attribute :external_id, :string do
      primary_key? true
      allow_nil? false
      public? true
    end

    attribute :meter_code, :string do
      allow_nil? false
      public? true
    end

    attribute :raw_kwh, :integer do
      allow_nil? false
      public? true
    end

    attribute :net_kwh, :integer do
      allow_nil? true
      default nil
      public? true
    end

    attribute :recorded_on, :date do
      allow_nil? false
      public? true
    end

    attribute :batch_ref, :string do
      allow_nil? false
      public? true
    end

    attribute :status, :atom do
      constraints one_of: [:pending, :normalized, :accepted, :rejected]
      allow_nil? false
      default :pending
      public? true
    end
  end

  identities do
    identity :unique_external_id, [:external_id],
      pre_check_with: Ingest.Pipeline,
      eager_check?: true
  end

  actions do
    defaults [:destroy, create: :*, update: :*]

    read :read do
      primary? true
      pagination keyset?: true, required?: false
    end

    create :ingest do
      primary? true
      accept [:external_id, :meter_code, :raw_kwh, :recorded_on, :batch_ref]

      change fn changeset, _context ->
        raw_kwh = Ash.Changeset.get_attribute(changeset, :raw_kwh)

        if is_integer(raw_kwh) and raw_kwh < 0 do
          Ash.Changeset.add_error(changeset,
            Ash.Error.Changes.InvalidAttribute.exception(
              field: :raw_kwh,
              message: "must be non-negative"
            )
          )
        else
          changeset
        end
      end
    end

    update :normalize do
      require_atomic? false
      atomic_upgrade? false

      change fn changeset, _context ->
        reading = changeset.data
        meter_code = reading.meter_code

        meter =
          Ingest.Pipeline.Meter
          |> Ash.Query.filter(code: meter_code)
          |> Ash.read!()
          |> List.first()

        if meter && meter.active do
          raw = reading.raw_kwh
          scale = meter.scale_bp
          net = Integer.floor_div(raw * scale + 5000, 10000)

          changeset
          |> Ash.Changeset.force_change_attribute(:net_kwh, net)
          |> Ash.Changeset.force_change_attribute(:status, :normalized)
        else
          changeset
          |> Ash.Changeset.force_change_attribute(:status, :rejected)
        end
      end
    end

    update :accept do
      require_atomic? true

      change {Ash.Resource.Change.Atomic,
              attribute: :status,
              expr:
                expr(
                  if status == :normalized do
                    :accepted
                  else
                    error(Ash.Error.Changes.InvalidAttribute, %{
                      field: :status,
                      message: "must be :normalized"
                    })
                  end
                )}
    end
  end
end
