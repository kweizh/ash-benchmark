defmodule Catalog.Library.Review do
  use Ash.Resource,
    domain: Catalog.Library,
    data_layer: Ash.DataLayer.Ets,
    extensions: [AshJsonApi.Resource]

  ets do
    private? false
  end

  json_api do
    type "review"

    routes do
      base "/reviews"

      get :read
      post :create
    end
  end

  attributes do
    uuid_primary_key :id

    attribute :rating, :integer do
      public? true
      allow_nil? false
      constraints min: 1, max: 5
    end

    attribute :body, :string do
      public? true
      allow_nil? true
    end
  end

  relationships do
    belongs_to :book, Catalog.Library.Book do
      public? true
      allow_nil? false
      attribute_writable? true
    end
  end

  actions do
    defaults [:read, :destroy]

    create :create do
      primary? true
      accept [:rating, :body]
    end
  end
end
