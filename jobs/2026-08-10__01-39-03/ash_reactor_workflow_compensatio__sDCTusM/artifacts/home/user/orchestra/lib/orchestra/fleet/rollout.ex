defmodule Orchestra.Fleet.Rollout do
  @moduledoc """
  A single fleet-wide software rollout.
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

    attribute :strategy, :atom do
      allow_nil? false
      public? true
      constraints one_of: [:canary, :blast]
    end

    attribute :status, :atom do
      default :pending
      public? true
      constraints one_of: [:pending, :running, :succeeded, :rolled_back]
    end

    attribute :deployed_node_count, :integer do
      default 0
      public? true
    end
  end

  actions do
    defaults [:read]

    create :create do
      accept [:name, :strategy]
    end

    update :mark_succeeded do
      accept [:deployed_node_count]
      change set_attribute(:status, :succeeded)
    end

    update :mark_failed do
      accept []

      argument :changeset, :term do
        allow_nil? true
      end

      change set_attribute(:status, :rolled_back)
      change set_attribute(:deployed_node_count, 0)
    end

    action :plan, :map do
      argument :targets, {:array, :map} do
        allow_nil? false
      end

      run fn input, _context ->
        Orchestra.Fleet.Rollout.Plan.run(input.arguments.targets)
      end
    end
  end
end
