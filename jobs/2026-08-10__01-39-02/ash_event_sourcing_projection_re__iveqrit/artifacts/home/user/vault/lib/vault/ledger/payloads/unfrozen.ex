defmodule Vault.Ledger.Payloads.Unfrozen do
  use Ash.Resource,
    data_layer: :embedded

  attributes do
    attribute :type, :string, allow_nil?: false, default: "unfrozen"
    attribute :note, :string, allow_nil?: true, constraints: [max_length: 120]
  end

  actions do
    defaults [:read]
    create :create do
      primary? true
      accept [:type, :note]
    end
  end
end
