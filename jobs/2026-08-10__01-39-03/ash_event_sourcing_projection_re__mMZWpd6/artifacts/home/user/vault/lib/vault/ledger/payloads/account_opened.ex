defmodule Vault.Ledger.Payloads.AccountOpened do
  @moduledoc false
  use Ash.Resource, data_layer: :embedded

  attributes do
    attribute :owner, :string do
      allow_nil? false
      public? true
      constraints min_length: 1
    end

    attribute :opening_balance_cents, :integer do
      allow_nil? false
      public? true
      constraints min: 0
    end
  end
end
