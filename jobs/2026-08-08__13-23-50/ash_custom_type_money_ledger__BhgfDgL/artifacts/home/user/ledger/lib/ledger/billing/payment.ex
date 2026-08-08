defmodule Ledger.Billing.Payment do
  @moduledoc """
  A payment recorded against an invoice.
  """

  use Ash.Resource,
    otp_app: :ledger,
    domain: Ledger.Billing,
    data_layer: Ash.DataLayer.Ets

  ets do
    private? true
  end

  attributes do
    uuid_primary_key :id

    attribute :amount, Ledger.Money.Type do
      allow_nil? false
      constraints currencies: [:usd, :eur, :jpy]
    end

    attribute :amount_minor, :integer do
      allow_nil? true
      writable? false
    end

    attribute :amount_currency, :atom do
      allow_nil? true
      writable? false
    end
  end

  relationships do
    belongs_to :invoice, Ledger.Billing.Invoice do
      allow_nil? false
      attribute_writable? true
    end
  end

  actions do
    defaults [:read, :destroy]

    create :record do
      accept [:amount, :invoice_id]

      change Ledger.Billing.Payment.Changes.DeriveMinorAndCurrency
    end
  end
end
