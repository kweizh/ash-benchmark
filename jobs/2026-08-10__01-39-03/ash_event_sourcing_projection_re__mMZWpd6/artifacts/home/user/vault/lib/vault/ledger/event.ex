defmodule Vault.Ledger.Event do
  @moduledoc """
  The append-only event log. This is the sole source of truth for the
  ledger; it is immutable (no update or destroy action of any kind).
  """

  use Ash.Resource,
    domain: Vault.Ledger,
    data_layer: Ash.DataLayer.Ets

  ets do
    private? true
  end

  attributes do
    uuid_primary_key :id

    attribute :sequence, :integer do
      allow_nil? false
      generated? true
      public? true
    end

    attribute :account_id, :string do
      allow_nil? false
      public? true
    end

    attribute :version, :integer do
      allow_nil? false
      public? true
    end

    attribute :payload, Vault.Ledger.Payload do
      allow_nil? false
      public? true
    end

    attribute :recorded_at, :utc_datetime_usec do
      allow_nil? false
      public? true
    end
  end

  identities do
    identity :unique_version, [:account_id, :version], pre_check_with: Vault.Ledger
    identity :unique_sequence, [:sequence], pre_check_with: Vault.Ledger
  end

  actions do
    read :read do
      primary? true
    end

    create :append do
      primary? true
      accept [:account_id, :version, :payload, :recorded_at]

      change Vault.Ledger.Event.Changes.AssignSequence

      validate Vault.Ledger.Event.Validations.VersionSequential
    end

    action :open_account, :struct do
      constraints instance_of: Vault.Ledger.CommandResult

      argument :account_id, :string, allow_nil?: false
      argument :owner, :string, allow_nil?: false
      argument :opening_balance_cents, :integer, allow_nil?: false, default: 0
      argument :recorded_at, :utc_datetime_usec, allow_nil?: true

      run Vault.Ledger.Commands.OpenAccount
    end

    action :deposit, :struct do
      constraints instance_of: Vault.Ledger.CommandResult

      argument :account_id, :string, allow_nil?: false
      argument :amount_cents, :integer, allow_nil?: false
      argument :recorded_at, :utc_datetime_usec, allow_nil?: true

      run Vault.Ledger.Commands.Deposit
    end

    action :withdraw, :struct do
      constraints instance_of: Vault.Ledger.CommandResult

      argument :account_id, :string, allow_nil?: false
      argument :amount_cents, :integer, allow_nil?: false
      argument :recorded_at, :utc_datetime_usec, allow_nil?: true

      run Vault.Ledger.Commands.Withdraw
    end

    action :transfer, :struct do
      constraints instance_of: Vault.Ledger.CommandResult

      argument :from_account_id, :string, allow_nil?: false
      argument :to_account_id, :string, allow_nil?: false
      argument :amount_cents, :integer, allow_nil?: false
      argument :recorded_at, :utc_datetime_usec, allow_nil?: true

      run Vault.Ledger.Commands.Transfer
    end

    action :freeze, :struct do
      constraints instance_of: Vault.Ledger.CommandResult

      argument :account_id, :string, allow_nil?: false

      argument :reason, :atom do
        allow_nil? false
        constraints one_of: [:fraud_review, :chargeback, :court_order]
      end

      argument :recorded_at, :utc_datetime_usec, allow_nil?: true

      run Vault.Ledger.Commands.Freeze
    end

    action :unfreeze, :struct do
      constraints instance_of: Vault.Ledger.CommandResult

      argument :account_id, :string, allow_nil?: false
      argument :note, :string, allow_nil?: true
      argument :recorded_at, :utc_datetime_usec, allow_nil?: true

      run Vault.Ledger.Commands.Unfreeze
    end
  end
end
