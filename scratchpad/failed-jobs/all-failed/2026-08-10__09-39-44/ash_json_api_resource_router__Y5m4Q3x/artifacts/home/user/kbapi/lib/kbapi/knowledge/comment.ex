defmodule Kbapi.Knowledge.Comment do
  use Ash.Resource,
    otp_app: :kbapi,
    domain: Kbapi.Knowledge,
    data_layer: Ash.DataLayer.Ets,
    authorizers: [Ash.Policy.Authorizer],
    extensions: [AshJsonApi.Resource]

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

  json_api do
    type "comment"

    includes [
      article: []
    ]

    routes do
      base "/comments"

      index :read, primary?: true
      get :read, primary?: true
      post :create
      delete :destroy
    end
  end

  policies do
    policy action_type([:read, :create]) do
      authorize_if always()
    end

    policy action_type([:update, :destroy]) do
      authorize_if expr(actor.role in [:editor, :admin])
    end
  end

  actions do
    default_accept []
    defaults [:read, :destroy]

    read :pending do
      filter expr(approved == false)
    end

    create :create do
      primary? true
      accept [:body, :article_id]
    end

    update :approve do
      accept []
      change set_attribute(:approved, true)
    end
  end
end
