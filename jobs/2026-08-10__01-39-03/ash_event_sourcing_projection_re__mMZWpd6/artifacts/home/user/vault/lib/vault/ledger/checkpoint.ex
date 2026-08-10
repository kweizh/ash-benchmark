defmodule Vault.Ledger.Checkpoint do
  @moduledoc """
  Tracks how far a named consumer has read through the event log.
  """

  use Ash.Resource,
    domain: Vault.Ledger,
    data_layer: Ash.DataLayer.Ets

  ets do
    private? true
  end

  attributes do
    attribute :name, :string do
      allow_nil? false
      primary_key? true
      public? true
    end

    attribute :sequence, :integer do
      allow_nil? false
      public? true
    end
  end

  actions do
    default_accept :*

    read :read do
      primary? true
    end

    create :create do
      primary? true
    end

    update :update do
      primary? true
    end

    destroy :destroy do
      primary? true
    end
  end
end
