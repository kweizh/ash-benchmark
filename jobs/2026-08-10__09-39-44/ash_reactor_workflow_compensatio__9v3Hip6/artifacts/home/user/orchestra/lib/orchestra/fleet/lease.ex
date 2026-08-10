defmodule Orchestra.Fleet.Lease do
  @moduledoc false

  use Ash.Resource,
    domain: Orchestra.Fleet,
    data_layer: Ash.DataLayer.Ets

  attributes do
    uuid_primary_key :id

    attribute :rollout_name, :string do
      allow_nil? false
      public? true
    end

    attribute :status, :atom do
      allow_nil? false
      constraints one_of: [:held, :released]
      default :held
      public? true
    end
  end

  actions do
    defaults [:read]

    create :create do
      accept [:rollout_name]
    end

    update :release do
      argument :changeset, :map do
        allow_nil? true
      end

      change set_attribute(:status, :released)
      require_atomic? false
    end
  end
end
