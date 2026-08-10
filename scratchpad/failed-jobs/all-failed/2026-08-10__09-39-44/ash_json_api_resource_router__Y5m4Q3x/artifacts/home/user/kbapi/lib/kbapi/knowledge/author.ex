defmodule Kbapi.Knowledge.Author do
  use Ash.Resource,
    otp_app: :kbapi,
    domain: Kbapi.Knowledge,
    data_layer: Ash.DataLayer.Ets,
    extensions: [AshJsonApi.Resource]

  ets do
    private? true
  end

  attributes do
    uuid_primary_key :id
    attribute :name, :string, allow_nil?: false, public?: true
    attribute :handle, :string, allow_nil?: false, public?: true
    attribute :bio, :string, public?: true

    attribute :role, :atom,
      public?: true,
      default: :reader,
      constraints: [one_of: [:reader, :editor, :admin]]
  end

  relationships do
    has_many :articles, Kbapi.Knowledge.Article do
      public? true
    end
  end

  json_api do
    type "author"

    includes [
      articles: []
    ]

    routes do
      base "/authors"

      index :read, primary?: true
      get :read, primary?: true
      post :create
      patch :update
      related :articles, :read, primary?: true
    end
  end

  actions do
    default_accept []
    defaults [:read, :destroy]

    create :create do
      primary? true
      accept [:name, :handle, :bio, :role]
    end

    update :update do
      primary? true
      accept [:name, :bio]
    end
  end
end
