defmodule Orchestra.Fleet.Rollout do
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

    attribute :strategy, :atom do
      allow_nil? false
      constraints one_of: [:canary, :blast]
      public? true
    end

    attribute :status, :atom do
      allow_nil? false
      constraints one_of: [:pending, :running, :succeeded, :rolled_back]
      default :pending
      public? true
    end

    attribute :deployed_node_count, :integer do
      allow_nil? false
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

    update :mark_rolled_back do
      argument :changeset, :map do
        allow_nil? true
      end

      change set_attribute(:status, :rolled_back)
      change set_attribute(:deployed_node_count, 0)
      require_atomic? false
    end

    action :plan_rollout, :map do
      argument :targets, {:array, :map} do
        allow_nil? false
      end

      run Orchestra.Rollout.Actions.PlanRollout
    end
  end
end
