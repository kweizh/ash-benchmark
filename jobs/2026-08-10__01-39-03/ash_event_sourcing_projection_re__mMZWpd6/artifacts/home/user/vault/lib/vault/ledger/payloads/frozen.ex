defmodule Vault.Ledger.Payloads.Frozen do
  @moduledoc false
  use Ash.Resource, data_layer: :embedded

  attributes do
    attribute :reason, :atom do
      allow_nil? false
      public? true
      constraints one_of: [:fraud_review, :chargeback, :court_order]
    end
  end
end
