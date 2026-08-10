defmodule Ingest.Pipeline.Meter do
  use Ash.Resource,
    otp_app: :ingest,
    domain: Ingest.Pipeline,
    data_layer: Ash.DataLayer.Ets

  ets do
    private? true
  end

  attributes do
    attribute :code, :string do
      primary_key? true
      allow_nil? false
      public? true
    end

    attribute :scale_bp, :integer do
      allow_nil? false
      default 10_000
      public? true
    end

    attribute :active, :boolean do
      allow_nil? false
      default true
      public? true
    end
  end

  actions do
    defaults [:read, :destroy, create: :*, update: :*]
    default_accept [:code, :scale_bp, :active]
  end
end
