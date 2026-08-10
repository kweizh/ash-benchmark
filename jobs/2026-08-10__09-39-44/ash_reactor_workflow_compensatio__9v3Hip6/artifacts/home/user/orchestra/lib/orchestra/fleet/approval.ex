defmodule Orchestra.Fleet.Approval do
  @moduledoc false

  use Ash.Resource,
    domain: Orchestra.Fleet,
    data_layer: Ash.DataLayer.Ets

  attributes do
    uuid_primary_key :id

    attribute :rollout_id, :uuid do
      allow_nil? false
      public? true
    end

    attribute :level, :atom do
      allow_nil? false
      constraints one_of: [:auto, :board]
      public? true
    end

    attribute :slots, :integer do
      allow_nil? false
      public? true
    end

    attribute :status, :atom do
      allow_nil? false
      constraints one_of: [:granted, :revoked]
      default :granted
      public? true
    end
  end

  actions do
    defaults [:read]

    create :create do
      accept [:rollout_id, :level, :slots]
    end

    update :revoke do
      argument :changeset, :map do
        allow_nil? true
      end

      change set_attribute(:status, :revoked)
      require_atomic? false
    end
  end
end
