defmodule Vault.Ledger.Payloads.Withdrawn do
  @moduledoc false
  use Ash.Resource, data_layer: :embedded

  attributes do
    attribute :amount_cents, :integer do
      allow_nil? false
      public? true
      constraints min: 1
    end
  end
end
