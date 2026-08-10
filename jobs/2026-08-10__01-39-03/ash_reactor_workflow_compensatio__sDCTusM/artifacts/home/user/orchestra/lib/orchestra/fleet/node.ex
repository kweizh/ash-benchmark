defmodule Orchestra.Fleet.Node do
  @moduledoc """
  An edge node which can have capacity reserved on it and have software
  deployed to it.
  """
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
      public? true
      constraints one_of: [:us_east, :eu_west, :ap_south]
    end

    attribute :slots_total, :integer do
      allow_nil? false
      public? true
    end

    attribute :slots_used, :integer do
      default 0
      public? true
    end

    attribute :state, :atom do
      default :idle
      public? true
      constraints one_of: [:idle, :reserved, :live]
    end

    attribute :deploy_failures_remaining, :integer do
      default 0
      public? true
    end
  end

  actions do
    defaults [:read]

    create :register do
      accept [:name, :region, :slots_total, :deploy_failures_remaining]
    end

    read :by_name do
      argument :name, :string, allow_nil?: false

      filter expr(name == ^arg(:name))
    end

    update :reserve do
      accept []
      require_atomic? false

      argument :slots, :integer do
        allow_nil? false
        constraints min: 1
      end

      change Orchestra.Fleet.Changes.ReserveCapacity
    end

    update :release_reservation do
      accept []
      require_atomic? false

      argument :changeset, :term do
        allow_nil? true
      end

      change Orchestra.Fleet.Changes.ReleaseReservation
    end

    update :go_live do
      accept []
      change set_attribute(:state, :live)
    end

    update :consume_failure do
      accept []
      require_atomic? false

      change fn changeset, _context ->
        current = changeset.data.deploy_failures_remaining

        Ash.Changeset.force_change_attribute(
          changeset,
          :deploy_failures_remaining,
          current - 1
        )
      end
    end
  end
end
