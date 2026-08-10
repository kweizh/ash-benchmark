defmodule Vault.Ledger.AccountProjection do
  use Ash.Resource,
    domain: Vault.Ledger,
    data_layer: Ash.DataLayer.Ets

  ets do
    private? true
  end

  attributes do
    attribute :account_id, :string, primary_key?: true, allow_nil?: false

    attribute :owner, :string, allow_nil?: false
    attribute :balance_cents, :integer, allow_nil?: false
    attribute :status, :atom, allow_nil?: false, constraints: [one_of: [:open, :frozen]]
    attribute :version, :integer, allow_nil?: false
    attribute :deposit_count, :integer, allow_nil?: false
    attribute :withdrawal_count, :integer, allow_nil?: false
    attribute :last_event_sequence, :integer, allow_nil?: false
    attribute :last_recorded_at, :utc_datetime_usec, allow_nil?: false
  end

  actions do
    defaults [:read, :destroy]

    create :create do
      primary? true
      accept [:account_id, :owner, :balance_cents, :status, :version, :deposit_count, :withdrawal_count, :last_event_sequence, :last_recorded_at]
    end

    update :update do
      primary? true
      require_atomic? false
      accept [:owner, :balance_cents, :status, :version, :deposit_count, :withdrawal_count, :last_event_sequence, :last_recorded_at]
    end
  end
end
