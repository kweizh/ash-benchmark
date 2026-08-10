defmodule Vault.Ledger.Payloads.Frozen do
  use Ash.Resource,
    data_layer: :embedded

  attributes do
    attribute :type, :string, allow_nil?: false, default: "frozen"
    attribute :reason, :atom, allow_nil?: false, constraints: [one_of: [:fraud_review, :chargeback, :court_order]]
  end

  actions do
    defaults [:read]
    create :create do
      primary? true
      accept [:type, :reason]
    end
  end
end
