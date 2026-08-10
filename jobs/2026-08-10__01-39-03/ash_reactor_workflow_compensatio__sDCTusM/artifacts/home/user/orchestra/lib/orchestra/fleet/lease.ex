defmodule Orchestra.Fleet.Lease do
  @moduledoc """
  A lease held for the duration of a single rollout run, guaranteeing that the
  rollout name is exclusively in use.
  """
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
      default :held
      public? true
      constraints one_of: [:held, :released]
    end
  end

  actions do
    defaults [:read]

    create :create do
      accept [:rollout_name]
    end

    update :release do
      accept []

      argument :changeset, :term do
        allow_nil? true
      end

      change set_attribute(:status, :released)
    end
  end
end
