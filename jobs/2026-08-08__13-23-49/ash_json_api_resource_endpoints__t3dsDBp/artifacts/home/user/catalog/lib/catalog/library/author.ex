defmodule Catalog.Library.Author do
  use Ash.Resource,
    domain: Catalog.Library,
    data_layer: Ash.DataLayer.Ets,
    extensions: [AshJsonApi.Resource],
    authorizers: [Ash.Policy.Authorizer]

  attributes do
    uuid_primary_key :id

    attribute :name, :string do
      allow_nil? false
      public? true
    end

    attribute :country, :string do
      public? true
    end
  end

  validations do
    validate string_length(:name, min: 1), message: "must not be empty"
  end

  relationships do
    has_many :books, Catalog.Library.Book do
      public? true
    end
  end

  actions do
    defaults [:read, :destroy]

    create :create do
      accept [:name, :country]
    end

    update :update do
      accept [:name, :country]
    end
  end

  policies do
    policy always() do
      authorize_if always()
    end
  end

  json_api do
    type "author"
    includes [books: [:reviews]]

    routes do
      base "/authors"

      get :read, primary?: true
      index :read
      post :create

      related :books, :read, primary?: true
      relationship :books, :read, primary?: true
    end
  end
end
