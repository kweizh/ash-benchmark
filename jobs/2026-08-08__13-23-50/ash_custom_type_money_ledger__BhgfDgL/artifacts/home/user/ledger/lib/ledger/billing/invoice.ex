defmodule Ledger.Billing.Invoice do
  @moduledoc """
  An invoice, priced in money.
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

    attribute :reference, :string do
      allow_nil? false
    end

    attribute :subtotal, Ledger.Money.Type do
      allow_nil? false
      constraints currencies: [:usd, :eur, :jpy]
    end

    attribute :adjustments, {:array, Ledger.Money.Type} do
      default []
      constraints items: [multiple_of: 5]
    end

    attribute :credit_limit, Ledger.Money.Usd do
      allow_nil? true
    end
  end

  relationships do
    has_many :payments, Ledger.Billing.Payment
  end

  aggregates do
    sum :paid_minor, :payments, :amount_minor do
      default 0
    end
  end

  calculations do
    calculate :total, Ledger.Money.Type, Ledger.Billing.Invoice.Calculations.Total
    calculate :balance, Ledger.Money.Type, Ledger.Billing.Invoice.Calculations.Balance
  end

  validations do
    validate Ledger.Billing.Invoice.Validations.AdjustmentsCurrency, on: [:create]
  end

  actions do
    defaults [:read, :destroy]

    create :issue do
      accept [:reference, :subtotal, :adjustments, :credit_limit]
    end

    update :apply_adjustment do
      require_atomic? false

      argument :adjustment, Ledger.Money.Type do
        allow_nil? false
      end

      validate Ledger.Billing.Invoice.Validations.AdjustmentCurrency

      change Ledger.Billing.Invoice.Changes.AppendAdjustment
    end

    action :price_for, Ledger.Money.Type do
      argument :unit_price, Ledger.Money.Type do
        allow_nil? false
      end

      argument :units, :integer do
        allow_nil? false
      end

      run fn input, _context ->
        Ledger.Money.multiply(input.arguments.unit_price, input.arguments.units)
      end
    end
  end
end
