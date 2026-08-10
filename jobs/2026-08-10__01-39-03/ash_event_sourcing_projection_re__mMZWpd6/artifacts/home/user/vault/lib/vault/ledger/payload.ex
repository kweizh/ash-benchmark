defmodule Vault.Ledger.Payload do
  @moduledoc """
  The typed event body for a `Vault.Ledger.Event`. A tagged union over the
  five event kinds, discriminated by a string `"type"` field.
  """

  use Ash.Type.NewType,
    subtype_of: :union,
    constraints: [
      types: [
        account_opened: [
          type: Vault.Ledger.Payloads.AccountOpened,
          tag: :type,
          tag_value: "account_opened"
        ],
        deposited: [
          type: Vault.Ledger.Payloads.Deposited,
          tag: :type,
          tag_value: "deposited"
        ],
        withdrawn: [
          type: Vault.Ledger.Payloads.Withdrawn,
          tag: :type,
          tag_value: "withdrawn"
        ],
        frozen: [
          type: Vault.Ledger.Payloads.Frozen,
          tag: :type,
          tag_value: "frozen"
        ],
        unfrozen: [
          type: Vault.Ledger.Payloads.Unfrozen,
          tag: :type,
          tag_value: "unfrozen"
        ]
      ]
    ]
end
