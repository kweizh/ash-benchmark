defmodule Orchestra.Fleet.Approval do
  @moduledoc """
  Tracks the approval granted (or revoked) for a rollout.
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

    attribute :level, :atom do
      allow_nil? false
      public? true
      constraints one_of: [:auto, :board]
    end

    attribute :slots, :integer do
      allow_nil? false
      public? true
    end

    attribute :status, :atom do
      default :granted
      public? true
      constraints one_of: [:granted, :revoked]
    end
  end

  actions do
    defaults [:read]

    create :create do
      accept [:rollout_id, :level, :slots]
    end

    update :revoke do
      accept []

      argument :changeset, :term do
        allow_nil? true
      end

      change set_attribute(:status, :revoked)
    end
  end
end
