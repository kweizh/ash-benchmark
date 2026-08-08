defmodule Outbox.Ledger.Account do
  @moduledoc """
  A ledger account.
  """

  use Ash.Resource,
    otp_app: :outbox,
    domain: Outbox.Ledger,
    data_layer: Ash.DataLayer.Ets,
    notifiers: [Outbox.Eventing.Notifier]

  ets do
    private? false
  end

  attributes do
    uuid_primary_key :id

    attribute :owner_id, :string, allow_nil?: false, public?: true
    attribute :name, :string, allow_nil?: false, public?: true
    attribute :balance, :integer, allow_nil?: false, default: 0, public?: true

    attribute :status, :atom,
      allow_nil?: false,
      default: :active,
      constraints: [one_of: [:active, :frozen, :closed]],
      public?: true
  end

  actions do
    defaults [:read]

    create :open do
      primary? true
      accept [:owner_id, :name, :balance]
    end

    update :rename do
      accept [:name]
    end

    update :freeze do
      accept []
      change set_attribute(:status, :frozen)
    end

    update :deposit do
      accept []
      argument :amount, :integer, allow_nil?: false
      change atomic_update(:balance, expr(balance + ^arg(:amount)))
    end

    update :withdraw do
      require_atomic? false
      accept []
      argument :amount, :integer, allow_nil?: false
      validate {Outbox.Ledger.SufficientFunds, []}
      change atomic_update(:balance, expr(balance - ^arg(:amount)))
    end

    destroy :close do
      primary? true
    end
  end
end
