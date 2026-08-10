defmodule Vault.Ledger.AccountState do
  @moduledoc """
  A pure, in-memory projection of a single account's stream, produced by
  folding its events. This struct is never stored authoritatively; it is
  always derived.
  """

  defstruct account_id: nil,
            owner: nil,
            balance_cents: 0,
            status: :absent,
            version: 0,
            deposit_count: 0,
            withdrawal_count: 0,
            last_event_type: nil,
            last_recorded_at: nil

  @type t :: %__MODULE__{
          account_id: String.t() | nil,
          owner: String.t() | nil,
          balance_cents: integer(),
          status: :absent | :open | :frozen,
          version: non_neg_integer(),
          deposit_count: non_neg_integer(),
          withdrawal_count: non_neg_integer(),
          last_event_type: atom() | nil,
          last_recorded_at: DateTime.t() | nil
        }
end
