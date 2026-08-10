defmodule Orchestra.Fleet.Placement do
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

    attribute :node_name, :string do
      allow_nil? false
      public? true
    end

    attribute :slots, :integer do
      allow_nil? false
      public? true
    end

    attribute :status, :atom do
      allow_nil? false
      constraints one_of: [:reserved, :deploying, :deployed, :released]
      default :reserved
      public? true
    end

    attribute :attempts, :integer do
      allow_nil? false
      default 0
      public? true
    end

    attribute :compensations, :integer do
      allow_nil? false
      default 0
      public? true
    end

    attribute :undos, :integer do
      allow_nil? false
      default 0
      public? true
    end
  end

  actions do
    defaults [:read]

    create :create do
      accept [:rollout_id, :node_name, :slots]
    end

    update :update do
      accept [:status, :attempts, :compensations, :undos]
      require_atomic? false
    end
  end
end
