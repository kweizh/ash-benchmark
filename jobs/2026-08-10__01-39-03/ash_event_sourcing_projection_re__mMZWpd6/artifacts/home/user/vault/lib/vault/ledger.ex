defmodule Vault.Ledger do
  @moduledoc """
  The Ash domain for the event-sourced ledger.
  """

  use Ash.Domain

  resources do
    resource Vault.Ledger.Event do
      define :append_event, action: :append
      define :list_events, action: :read

      define :open_account, action: :open_account, args: [:account_id, :owner]
      define :deposit, action: :deposit, args: [:account_id, :amount_cents]
      define :withdraw, action: :withdraw, args: [:account_id, :amount_cents]

      define :transfer,
        action: :transfer,
        args: [:from_account_id, :to_account_id, :amount_cents]

      define :freeze_account, action: :freeze, args: [:account_id, :reason]
      define :unfreeze_account, action: :unfreeze, args: [:account_id]
    end

    resource Vault.Ledger.Snapshot
    resource Vault.Ledger.AccountProjection
    resource Vault.Ledger.Checkpoint
  end
end
