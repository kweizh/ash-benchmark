defmodule Vault.Ledger.AccountState do
  defstruct [
    account_id: nil,
    owner: nil,
    balance_cents: 0,
    status: :absent,
    version: 0,
    deposit_count: 0,
    withdrawal_count: 0,
    last_event_type: nil,
    last_recorded_at: nil
  ]
end
