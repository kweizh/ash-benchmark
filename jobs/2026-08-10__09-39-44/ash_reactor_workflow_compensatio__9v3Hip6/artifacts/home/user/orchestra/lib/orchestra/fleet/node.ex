defmodule Orchestra.Fleet.Node do
  @moduledoc false

  use Ash.Resource,
    domain: Orchestra.Fleet,
    data_layer: Ash.DataLayer.Ets

  attributes do
    uuid_primary_key :id

    attribute :name, :string do
      allow_nil? false
      public? true
    end

    attribute :region, :atom do
      allow_nil? false
      constraints one_of: [:us_east, :eu_west, :ap_south]
      public? true
    end

    attribute :slots_total, :integer do
      allow_nil? false
      public? true
    end

    attribute :slots_used, :integer do
      allow_nil? false
      default 0
      public? true
    end

    attribute :state, :atom do
      allow_nil? false
      constraints one_of: [:idle, :reserved, :live]
      default :idle
      public? true
    end

    attribute :deploy_failures_remaining, :integer do
      allow_nil? false
      default 0
      public? true
    end
  end

  actions do
    defaults [:read]

    create :register do
      accept [:name, :region, :slots_total, :deploy_failures_remaining]
    end

    read :get_by_name do
      argument :node_name, :string do
        allow_nil? false
      end

      filter expr(name == ^arg(:node_name))
    end

    update :reserve do
      accept [:slots_used]
      change set_attribute(:state, :reserved)
    end

    update :release_reservation do
      argument :changeset, :map do
        allow_nil? true
      end

      change Orchestra.Rollout.Changes.ReleaseReservation
      require_atomic? false
    end

    update :update do
      accept [:slots_used, :state, :deploy_failures_remaining]
      require_atomic? false
    end
  end
end
