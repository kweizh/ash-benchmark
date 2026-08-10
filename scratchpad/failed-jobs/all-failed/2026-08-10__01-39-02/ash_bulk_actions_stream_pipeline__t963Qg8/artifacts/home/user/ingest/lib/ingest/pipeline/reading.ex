defmodule Ingest.Pipeline.Reading do
  use Ash.Resource,
    otp_app: :ingest,
    domain: Ingest.Pipeline,
    data_layer: Ash.DataLayer.Ets

  ets do
    private?(true)
  end

  attributes do
    attribute :external_id, :string do
      primary_key?(true)
      allow_nil?(false)
      public?(true)
    end

    attribute :meter_code, :string do
      allow_nil?(false)
      public?(true)
    end

    attribute :raw_kwh, :integer do
      allow_nil?(false)
      constraints(min: 0)
      public?(true)
    end

    attribute :net_kwh, :integer do
      allow_nil?(true)
      public?(true)
    end

    attribute :recorded_on, :date do
      allow_nil?(false)
      public?(true)
    end

    attribute :batch_ref, :string do
      allow_nil?(false)
      public?(true)
    end

    attribute :status, :atom do
      allow_nil?(false)
      constraints(one_of: [:pending, :normalized, :accepted, :rejected])
      default(:pending)
      public?(true)
    end
  end

  actions do
    defaults([:destroy, update: :*])

    read :read do
      primary?(true)

      pagination do
        keyset?(true)
        default_limit(100)
      end
    end

    create :ingest do
      accept([:external_id, :meter_code, :raw_kwh, :recorded_on, :batch_ref])
      validate(Ingest.Pipeline.Validations.UniqueExternalId)
    end

    update :normalize do
      require_atomic?(false)
      change(Ingest.Pipeline.Changes.Normalize)
    end

    update :accept do
      require_atomic?(true)
      change(set_attribute(:status, :accepted))
      validate(Ingest.Pipeline.Validations.StatusIsNormalized)
    end
  end
end
