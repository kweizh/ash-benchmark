defmodule Kbapi.Knowledge.Comment do
  use Ash.Resource,
    otp_app: :kbapi,
    domain: Kbapi.Knowledge,
    data_layer: Ash.DataLayer.Ets

  ets do
    private? true
  end

  attributes do
    uuid_primary_key :id
    attribute :body, :string, allow_nil?: false, public?: true, constraints: [min_length: 2]
    attribute :approved, :boolean, public?: true, default: false
  end

  relationships do
    belongs_to :article, Kbapi.Knowledge.Article do
      public? true
      allow_nil? false
      attribute_writable? true
    end
  end

  actions do
    default_accept []
    defaults [:read, :destroy]

    create :create do
      primary? true
      accept [:body, :article_id]
    end
  end
end
