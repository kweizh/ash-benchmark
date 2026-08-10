defmodule SlaLab.Ops.Shipment do
  use Ash.Resource,
    otp_app: :sla_lab,
    domain: SlaLab.Ops,
    data_layer: Ash.DataLayer.Ets,
    authorizers: [Ash.Policy.Authorizer]

  ets do
    private? true
  end

  attributes do
    uuid_primary_key :id
    attribute :reference, :string, allow_nil?: false, public?: true
    attribute :origin_zone, :string, allow_nil?: false, public?: true
    attribute :destination_zone, :string, allow_nil?: false, public?: true
    attribute :promised_hours, :integer, allow_nil?: false, public?: true
    attribute :actual_hours, :integer, public?: true

    attribute :priority, :atom,
      default: :standard,
      public?: true,
      constraints: [one_of: [:standard, :express, :critical]]
  end

  relationships do
    belongs_to :carrier, SlaLab.Ops.Carrier do
      public? true
      attribute_writable? true
    end
  end

  actions do
    defaults [:read, :destroy, create: :*]

    read :on_route do
      argument :route, :string, allow_nil?: false

      filter expr(route_key(origin_zone, destination_zone) == ^arg(:route))
    end

    update :record_delivery do
      accept [:actual_hours]
      require_atomic? true

      validate {SlaLab.Ops.Validations.RatioWithin, max_bps: 15_000}
    end
  end

  calculations do
    calculate :route_key, :string, expr(route_key(origin_zone, destination_zone)) do
      public? true
    end

    calculate :sla_ratio_bps, :integer,
              expr(ratio_bps(actual_hours, promised_hours)) do
      public? true
    end

    calculate :status_label, :string,
              expr(
                if is_nil(actual_hours) do
                  "pending"
                else
                  if ratio_bps(actual_hours, promised_hours) > 10_000 do
                    "breached"
                  else
                    "met"
                  end
                end
              ) do
      public? true
    end
  end

  policies do
    bypass action_type(:read) do
      authorize_if actor_attribute_equals(:role, :admin)
    end

    policy action_type(:read) do
      forbid_if actor_absent()
      authorize_if expr(actor(:home_route) == route_key(origin_zone, destination_zone))
    end

    policy action_type([:create, :update, :destroy]) do
      authorize_if always()
    end
  end
end
