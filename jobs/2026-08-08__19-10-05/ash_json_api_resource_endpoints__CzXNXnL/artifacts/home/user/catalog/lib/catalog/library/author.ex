defmodule Catalog.Library.Author do
  use Ash.Resource,
    domain: Catalog.Library,
    data_layer: Ash.DataLayer.Ets,
    extensions: [AshJsonApi.Resource]

  ets do
    private? false
  end

  json_api do
    type "author"

    includes [
      books: [
        reviews: []
      ]
    ]

    routes do
      base "/authors"

      index :read
      get :read
      post :create
      related :books, :read
      relationship :books, :read
    end
  end

  attributes do
    uuid_primary_key :id

    attribute :name, :string do
      public? true
      allow_nil? false
      constraints min_length: 1
    end

    attribute :country, :string do
      public? true
      allow_nil? true
    end
  end

  relationships do
    has_many :books, Catalog.Library.Book do
      public? true
    end
  end

  actions do
    defaults [:read, :destroy]

    create :create do
      primary? true
      accept [:name, :country]
    end
  end
end
