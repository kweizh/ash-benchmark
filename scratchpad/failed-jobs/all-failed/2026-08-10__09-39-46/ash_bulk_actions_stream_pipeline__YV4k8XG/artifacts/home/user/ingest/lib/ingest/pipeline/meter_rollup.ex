defmodule Ingest.Pipeline.MeterRollup do
  use Ash.Resource,
    otp_app: :ingest,
    domain: Ingest.Pipeline,
    data_layer: Ash.DataLayer.Ets

  ets do
    private? true
  end

  attributes do
    attribute :meter_code, :string do
      primary_key? true
      allow_nil? false
      public? true
    end

    attribute :total_net_kwh, :integer do
      allow_nil? false
      default 0
      public? true
    end

    attribute :reading_count, :integer do
      allow_nil? false
      default 0
      public? true
    end

    attribute :revision, :integer do
      allow_nil? false
      default 0
      public? true
    end

    attribute :last_batch_ref, :string do
      allow_nil? true
      default nil
      public? true
    end
  end

  actions do
    defaults [:read, :destroy, create: :*, update: :*]
  end
end
