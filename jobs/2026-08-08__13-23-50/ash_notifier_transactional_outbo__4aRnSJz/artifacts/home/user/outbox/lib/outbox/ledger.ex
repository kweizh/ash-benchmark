defmodule Outbox.Ledger do
  @moduledoc """
  The ledger domain: accounts and transfers, stored in memory.
  """

  use Ash.Domain, otp_app: :outbox

  resources do
    resource Outbox.Ledger.Account
    resource Outbox.Ledger.Transfer
  end
end
