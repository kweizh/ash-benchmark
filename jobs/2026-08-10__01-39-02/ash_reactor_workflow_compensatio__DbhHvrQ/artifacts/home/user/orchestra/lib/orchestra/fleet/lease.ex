defmodule Orchestra.Fleet.Lease do
  use Ash.Resource,
    domain: Orchestra.Fleet,
    data_layer: Ash.DataLayer.Ets

  attributes do
    uuid_primary_key :id
    attribute :rollout_name, :string, allow_nil?: false
    attribute :status, :atom, default: :held, allow_nil?: false, constraints: [one_of: [:held, :released]]
  end

  actions do
    defaults [:read, :destroy]

    create :create do
      accept [:rollout_name, :status]
      primary? true
    end

    update :update do
      accept [:rollout_name, :status]
      primary? true
    end

    update :release do
      argument :changeset, :term
      change set_attribute(:status, :released)
    end
  end
end
