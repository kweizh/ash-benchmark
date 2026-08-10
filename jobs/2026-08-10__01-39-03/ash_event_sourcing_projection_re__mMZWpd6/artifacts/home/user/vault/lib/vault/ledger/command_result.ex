defmodule Vault.Ledger.CommandResult do
  @moduledoc """
  The result of executing a ledger command. Not an Ash resource, just a
  plain struct returned by the generic command actions on `Vault.Ledger.Event`.
  """

  defstruct [:command, :account_id, :appended, :state]

  @type t :: %__MODULE__{
          command: atom(),
          account_id: String.t(),
          appended: [Vault.Ledger.Event.t()],
          state: Vault.Ledger.AccountState.t()
        }
end
