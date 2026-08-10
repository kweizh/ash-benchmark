defmodule Vault.Ledger.Payloads.Deposited do
  use Ash.Resource,
    data_layer: :embedded

  attributes do
    attribute :type, :string, allow_nil?: false, default: "deposited"
    attribute :amount_cents, :integer, allow_nil?: false, constraints: [min: 1]
  end

  actions do
    defaults [:read]
    create :create do
      primary? true
      accept [:type, :amount_cents]
    end
  end
end
