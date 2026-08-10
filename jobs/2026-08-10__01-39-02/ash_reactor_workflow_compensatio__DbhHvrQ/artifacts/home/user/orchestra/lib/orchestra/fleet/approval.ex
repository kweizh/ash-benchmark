defmodule Orchestra.Fleet.Approval do
  use Ash.Resource,
    domain: Orchestra.Fleet,
    data_layer: Ash.DataLayer.Ets

  attributes do
    uuid_primary_key :id
    attribute :rollout_id, :uuid, allow_nil?: false
    attribute :level, :atom, allow_nil?: false, constraints: [one_of: [:auto, :board]]
    attribute :slots, :integer, allow_nil?: false
    attribute :status, :atom, default: :granted, allow_nil?: false, constraints: [one_of: [:granted, :revoked]]
  end

  actions do
    defaults [:read, :destroy]

    create :create do
      accept [:rollout_id, :level, :slots, :status]
      primary? true
    end

    update :update do
      accept [:rollout_id, :level, :slots, :status]
      primary? true
    end

    update :revoke do
      argument :changeset, :term
      change set_attribute(:status, :revoked)
    end
  end
end
