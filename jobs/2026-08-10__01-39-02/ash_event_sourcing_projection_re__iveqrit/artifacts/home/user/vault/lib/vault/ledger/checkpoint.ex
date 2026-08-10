defmodule Vault.Ledger.Checkpoint do
  use Ash.Resource,
    domain: Vault.Ledger,
    data_layer: Ash.DataLayer.Ets

  ets do
    private? true
  end

  attributes do
    attribute :name, :string, primary_key?: true, allow_nil?: false
    attribute :sequence, :integer, allow_nil?: false
  end

  actions do
    defaults [:read, :destroy]

    create :create do
      primary? true
      accept [:name, :sequence]
    end

    update :update do
      primary? true
      require_atomic? false
      accept [:sequence]
    end
  end
end
