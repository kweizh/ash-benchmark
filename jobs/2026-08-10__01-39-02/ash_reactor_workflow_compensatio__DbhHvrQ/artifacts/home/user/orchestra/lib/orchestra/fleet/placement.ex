defmodule Orchestra.Fleet.Placement do
  use Ash.Resource,
    domain: Orchestra.Fleet,
    data_layer: Ash.DataLayer.Ets

  attributes do
    uuid_primary_key :id
    attribute :rollout_id, :uuid, allow_nil?: false
    attribute :node_name, :string, allow_nil?: false
    attribute :slots, :integer, allow_nil?: false
    attribute :status, :atom, default: :reserved, allow_nil?: false, constraints: [one_of: [:reserved, :deploying, :deployed, :released]]
    attribute :attempts, :integer, default: 0, allow_nil?: false
    attribute :compensations, :integer, default: 0, allow_nil?: false
    attribute :undos, :integer, default: 0, allow_nil?: false
  end

  actions do
    defaults [:read, :destroy]

    create :create do
      accept [:rollout_id, :node_name, :slots, :status, :attempts, :compensations, :undos]
      primary? true
    end

    update :update do
      accept [:rollout_id, :node_name, :slots, :status, :attempts, :compensations, :undos]
      primary? true
    end
  end
end
