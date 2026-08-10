defmodule Vault.Ledger.Snapshot do
  @moduledoc """
  A cached fold result for a single account at a specific version, plus a
  checksum, so that the fold can be resumed cheaply. Written only by the
  command layer.
  """

  use Ash.Resource,
    domain: Vault.Ledger,
    data_layer: Ash.DataLayer.Ets

  ets do
    private? true
  end

  attributes do
    uuid_primary_key :id

    attribute :account_id, :string do
      allow_nil? false
      public? true
    end

    attribute :version, :integer do
      allow_nil? false
      public? true
    end

    attribute :sequence, :integer do
      allow_nil? false
      public? true
    end

    attribute :state, :map do
      allow_nil? false
      public? true
    end

    attribute :checksum, :string do
      allow_nil? false
      public? true
    end
  end

  identities do
    identity :unique_version, [:account_id, :version], pre_check_with: Vault.Ledger
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
      require_atomic? false
    end

    destroy :destroy do
      primary? true
    end
  end
end
