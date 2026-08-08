defmodule Catalog.Library.Review do
  use Ash.Resource,
    domain: Catalog.Library,
    data_layer: Ash.DataLayer.Ets,
    extensions: [AshJsonApi.Resource],
    authorizers: [Ash.Policy.Authorizer]

  attributes do
    uuid_primary_key :id

    attribute :rating, :integer do
      allow_nil? false
      public? true
    end

    attribute :body, :string do
      public? true
    end
  end

  validations do
    validate numericality(:rating, greater_than_or_equal_to: 1, less_than_or_equal_to: 5)
  end

  relationships do
    belongs_to :book, Catalog.Library.Book do
      allow_nil? false
      public? true
    end
  end

  actions do
    defaults [:read, :destroy]

    create :create do
      accept [:rating, :body]
      argument :book, :uuid, allow_nil?: false
      change manage_relationship(:book, type: :append_and_remove)
    end

    update :update do
      accept [:rating, :body]
    end
  end

  policies do
    policy always() do
      authorize_if always()
    end
  end

  json_api do
    type "review"
    includes [:book]
    hide_fields [:book_id]

    routes do
      base "/reviews"

      get :read, primary?: true
      post :create, relationship_arguments: [{:id, :book}]
    end
  end
end
