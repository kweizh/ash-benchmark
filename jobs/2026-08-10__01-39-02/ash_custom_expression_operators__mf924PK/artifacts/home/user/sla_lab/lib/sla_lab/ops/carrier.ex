defmodule SlaLab.Ops.Carrier do
  use Ash.Resource,
    otp_app: :sla_lab,
    domain: SlaLab.Ops,
    data_layer: Ash.DataLayer.Ets

  ets do
    private? true
  end

  attributes do
    uuid_primary_key :id
    attribute :code, :string, allow_nil?: false, public?: true

    attribute :tier, :atom,
      default: :bronze,
      public?: true,
      constraints: [one_of: [:bronze, :silver, :gold]]
  end

  relationships do
    has_many :shipments, SlaLab.Ops.Shipment do
      public? true
    end
  end

  aggregates do
    count :delivered_count, :shipments do
      filter expr(not is_nil(actual_hours))
    end

    count :breach_count, :shipments do
      filter expr(sla_ratio_bps > 10_000)
    end
  end

  calculations do
    calculate :breach_rate_bps, :integer, expr(ratio_bps(breach_count, delivered_count)) do
      public? true
    end
  end

  actions do
    defaults [:read, :destroy, create: :*, update: :*]
  end
end
