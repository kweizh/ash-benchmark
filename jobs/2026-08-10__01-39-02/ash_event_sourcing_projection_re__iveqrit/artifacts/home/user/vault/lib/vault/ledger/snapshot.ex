defmodule Vault.Ledger.Snapshot do
  use Ash.Resource,
    domain: Vault.Ledger,
    data_layer: Ash.DataLayer.Ets

  ets do
    private? true
  end

  attributes do
    uuid_primary_key :id

    attribute :account_id, :string, allow_nil?: false
    attribute :version, :integer, allow_nil?: false
    attribute :sequence, :integer, allow_nil?: false
    attribute :state, :map, allow_nil?: false
    attribute :checksum, :string, allow_nil?: false
  end

  actions do
    defaults [:read]

    create :create do
      primary? true
      accept [:account_id, :version, :sequence, :state, :checksum]
    end

    update :update do
      primary? true
      require_atomic? false
      accept [:account_id, :version, :sequence, :state, :checksum]
    end
  end

  identities do
    identity :unique_account_version, [:account_id, :version], pre_check_with: Vault.Ledger
  end
end
