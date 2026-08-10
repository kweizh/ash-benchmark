defmodule Vault.Ledger.CommandResult do
  defstruct [:command, :account_id, :appended, :state]
end
