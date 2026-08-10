defmodule Catering.Orders.Customer do
  use Ash.Resource,
    otp_app: :catering,
    domain: Catering.Orders,
    data_layer: Ash.DataLayer.Ets

  ets do
    private? true
  end

  attributes do
    uuid_primary_key :id
    attribute :name, :string, allow_nil?: false, public?: true
    attribute :email, :string, allow_nil?: false, public?: true
  end

  actions do
    defaults [:read, :destroy]
    default_accept [:name, :email]

    create :register do
      primary? true
      accept [:name, :email]
    end

    update :amend do
      primary? true
      accept [:name, :email]
    end
  end
end
