defmodule Vault.Ledger.AccountProjection do
  @moduledoc """
  The rebuildable read model for an account, kept up to date exclusively by
  `Vault.Ledger.Projector.catch_up/0` and `Vault.Ledger.Projector.rebuild_all/0`.
  """

  use Ash.Resource,
    domain: Vault.Ledger,
    data_layer: Ash.DataLayer.Ets

  ets do
    private? true
  end

  attributes do
    attribute :account_id, :string do
      allow_nil? false
      primary_key? true
      public? true
    end

    attribute :owner, :string do
      allow_nil? false
      public? true
    end

    attribute :balance_cents, :integer do
      allow_nil? false
      public? true
    end

    attribute :status, :atom do
      allow_nil? false
      public? true
      constraints one_of: [:open, :frozen]
    end

    attribute :version, :integer do
      allow_nil? false
      public? true
    end

    attribute :deposit_count, :integer do
      allow_nil? false
      public? true
    end

    attribute :withdrawal_count, :integer do
      allow_nil? false
      public? true
    end

    attribute :last_event_sequence, :integer do
      allow_nil? false
      public? true
    end

    attribute :last_recorded_at, :utc_datetime_usec do
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
