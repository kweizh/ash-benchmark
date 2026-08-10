defmodule Vault.Ledger.Payloads.Withdrawn do
  use Ash.Resource,
    data_layer: :embedded

  attributes do
    attribute :type, :string, allow_nil?: false, default: "withdrawn"
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
