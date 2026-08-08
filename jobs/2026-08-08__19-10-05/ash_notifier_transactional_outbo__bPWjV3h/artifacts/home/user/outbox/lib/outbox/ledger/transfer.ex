defmodule Outbox.Ledger.Transfer do
  @moduledoc """
  A transfer between two ledger accounts.
  """

  use Ash.Resource,
    otp_app: :outbox,
    domain: Outbox.Ledger,
    data_layer: Ash.DataLayer.Ets,
    simple_notifiers: [Outbox.Eventing.Notifier]

  ets do
    private? false
  end

  attributes do
    uuid_primary_key :id

    attribute :from_account_id, :string, allow_nil?: false, public?: true
    attribute :to_account_id, :string, allow_nil?: false, public?: true
    attribute :amount, :integer, allow_nil?: false, public?: true

    attribute :state, :atom,
      allow_nil?: false,
      default: :pending,
      constraints: [one_of: [:pending, :settled]],
      public?: true
  end

  actions do
    defaults [:read, :destroy]

    create :record do
      primary? true
      accept [:from_account_id, :to_account_id, :amount]
    end

    update :settle do
      accept []
      change set_attribute(:state, :settled)
    end
  end
end
