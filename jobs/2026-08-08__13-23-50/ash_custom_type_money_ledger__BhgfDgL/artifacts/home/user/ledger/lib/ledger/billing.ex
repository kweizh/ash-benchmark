defmodule Ledger.Billing do
  @moduledoc """
  The billing domain.
  """
  use Ash.Domain, otp_app: :ledger

  resources do
    resource Ledger.Billing.Invoice do
      define :issue_invoice, action: :issue
      define :get_invoice, action: :read, get_by: [:id]
      define :list_invoices, action: :read
      define :apply_adjustment, action: :apply_adjustment, args: [:adjustment]
      define :price_for, action: :price_for, args: [:unit_price, :units]
    end

    resource Ledger.Billing.Payment do
      define :record_payment, action: :record
    end
  end
end
