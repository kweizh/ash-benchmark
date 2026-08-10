defmodule Vault.Ledger.Payloads.AccountOpened do
  use Ash.Resource,
    data_layer: :embedded

  attributes do
    attribute :type, :string, allow_nil?: false, default: "account_opened"
    attribute :owner, :string, allow_nil?: false, constraints: [min_length: 1]
    attribute :opening_balance_cents, :integer, allow_nil?: false, constraints: [min: 0]
  end

  actions do
    defaults [:read]
    create :create do
      primary? true
      accept [:type, :owner, :opening_balance_cents]
    end
  end
end
