defmodule Vault.Ledger do
  use Ash.Domain

  resources do
    resource Vault.Ledger.Event do
      define :open_account, args: [:account_id, :owner]
      define :deposit, args: [:account_id, :amount_cents]
      define :withdraw, args: [:account_id, :amount_cents]
      define :transfer, args: [:from_account_id, :to_account_id, :amount_cents]
      define :freeze_account, action: :freeze, args: [:account_id, :reason]
      define :unfreeze_account, action: :unfreeze, args: [:account_id]
      define :append_event, action: :append
      define :list_events, action: :read
    end

    resource Vault.Ledger.Snapshot
    resource Vault.Ledger.AccountProjection
    resource Vault.Ledger.Checkpoint
  end
end
