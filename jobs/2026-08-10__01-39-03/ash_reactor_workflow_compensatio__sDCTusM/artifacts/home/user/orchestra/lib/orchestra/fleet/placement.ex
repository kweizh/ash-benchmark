defmodule Orchestra.Fleet.Placement do
  @moduledoc """
  Tracks the reservation and deployment of a single rollout target node.
  """
  use Ash.Resource,
    domain: Orchestra.Fleet,
    data_layer: Ash.DataLayer.Ets

  attributes do
    uuid_primary_key :id

    attribute :rollout_id, :uuid do
      allow_nil? false
      public? true
    end

    attribute :node_name, :string do
      allow_nil? false
      public? true
    end

    attribute :slots, :integer do
      allow_nil? false
      public? true
    end

    attribute :status, :atom do
      default :reserved
      public? true
      constraints one_of: [:reserved, :deploying, :deployed, :released]
    end

    attribute :attempts, :integer do
      default 0
      public? true
    end

    attribute :compensations, :integer do
      default 0
      public? true
    end

    attribute :undos, :integer do
      default 0
      public? true
    end
  end

  actions do
    defaults [:read]

    create :create do
      accept [:rollout_id, :node_name, :slots]
    end

    update :begin_attempt do
      accept []
      require_atomic? false
      change set_attribute(:status, :deploying)

      change fn changeset, _context ->
        Ash.Changeset.force_change_attribute(changeset, :attempts, changeset.data.attempts + 1)
      end
    end

    update :mark_deployed do
      accept []
      change set_attribute(:status, :deployed)
    end

    update :mark_compensated do
      accept []
      require_atomic? false
      change set_attribute(:status, :reserved)

      change fn changeset, _context ->
        Ash.Changeset.force_change_attribute(
          changeset,
          :compensations,
          changeset.data.compensations + 1
        )
      end
    end

    update :mark_released do
      accept []
      require_atomic? false
      change set_attribute(:status, :released)

      change fn changeset, _context ->
        Ash.Changeset.force_change_attribute(changeset, :undos, changeset.data.undos + 1)
      end
    end
  end
end
