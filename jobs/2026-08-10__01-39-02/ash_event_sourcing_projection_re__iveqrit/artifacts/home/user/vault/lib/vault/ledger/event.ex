defmodule Vault.Ledger.Event do
  use Ash.Resource,
    domain: Vault.Ledger,
    data_layer: Ash.DataLayer.Ets

  ets do
    private? true
  end

  attributes do
    uuid_primary_key :id

    attribute :sequence, :integer, allow_nil?: false
    attribute :account_id, :string, allow_nil?: false
    attribute :version, :integer, allow_nil?: false
    attribute :payload, Vault.Ledger.Payload, allow_nil?: false
    attribute :recorded_at, :utc_datetime_usec, allow_nil?: false
  end

  actions do
    defaults [:read]

    create :append do
      accept [:account_id, :version, :payload, :recorded_at]
      validate Vault.Ledger.Validations.VersionSequence
      change Vault.Ledger.Changes.DeriveSequence
    end

    action :open_account, :struct do
      constraints instance_of: Vault.Ledger.CommandResult
      argument :account_id, :string, allow_nil?: false
      argument :owner, :string, allow_nil?: false
      argument :opening_balance_cents, :integer, default: 0
      argument :recorded_at, :utc_datetime_usec, allow_nil?: true

      run fn input, _context ->
        Vault.Ledger.Commands.run_command(:open_account, input.arguments)
      end
    end

    action :deposit, :struct do
      constraints instance_of: Vault.Ledger.CommandResult
      argument :account_id, :string, allow_nil?: false
      argument :amount_cents, :integer, allow_nil?: false
      argument :recorded_at, :utc_datetime_usec, allow_nil?: true

      run fn input, _context ->
        Vault.Ledger.Commands.run_command(:deposit, input.arguments)
      end
    end

    action :withdraw, :struct do
      constraints instance_of: Vault.Ledger.CommandResult
      argument :account_id, :string, allow_nil?: false
      argument :amount_cents, :integer, allow_nil?: false
      argument :recorded_at, :utc_datetime_usec, allow_nil?: true

      run fn input, _context ->
        Vault.Ledger.Commands.run_command(:withdraw, input.arguments)
      end
    end

    action :transfer, :struct do
      constraints instance_of: Vault.Ledger.CommandResult
      argument :from_account_id, :string, allow_nil?: false
      argument :to_account_id, :string, allow_nil?: false
      argument :amount_cents, :integer, allow_nil?: false
      argument :recorded_at, :utc_datetime_usec, allow_nil?: true

      run fn input, _context ->
        Vault.Ledger.Commands.run_command(:transfer, input.arguments)
      end
    end

    action :freeze, :struct do
      constraints instance_of: Vault.Ledger.CommandResult
      argument :account_id, :string, allow_nil?: false
      argument :reason, :atom, allow_nil?: false
      argument :recorded_at, :utc_datetime_usec, allow_nil?: true

      run fn input, _context ->
        Vault.Ledger.Commands.run_command(:freeze, input.arguments)
      end
    end

    action :unfreeze, :struct do
      constraints instance_of: Vault.Ledger.CommandResult
      argument :account_id, :string, allow_nil?: false
      argument :note, :string, allow_nil?: true
      argument :recorded_at, :utc_datetime_usec, allow_nil?: true

      run fn input, _context ->
        Vault.Ledger.Commands.run_command(:unfreeze, input.arguments)
      end
    end
  end

  identities do
    identity :unique_account_version, [:account_id, :version], pre_check_with: Vault.Ledger
    identity :unique_sequence, [:sequence], pre_check_with: Vault.Ledger
  end
end
