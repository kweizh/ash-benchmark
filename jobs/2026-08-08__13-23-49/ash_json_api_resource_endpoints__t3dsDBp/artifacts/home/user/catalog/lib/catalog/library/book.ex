defmodule Catalog.Library.Book do
  use Ash.Resource,
    domain: Catalog.Library,
    data_layer: Ash.DataLayer.Ets,
    extensions: [AshJsonApi.Resource],
    authorizers: [Ash.Policy.Authorizer]

  attributes do
    uuid_primary_key :id

    attribute :title, :string do
      allow_nil? false
      public? true
    end

    attribute :shelf, :string do
      allow_nil? false
      public? true
    end

    attribute :year, :integer do
      allow_nil? false
      public? true
    end

    attribute :price_cents, :integer do
      allow_nil? false
      public? true
    end

    attribute :restricted, :boolean do
      allow_nil? false
      default false
      public? true
    end
  end

  validations do
    validate string_length(:title, min: 1), message: "must not be empty"
    validate string_length(:shelf, min: 1), message: "must not be empty"
    validate numericality(:year, greater_than_or_equal_to: 1450, less_than_or_equal_to: 2100)
    validate numericality(:price_cents, greater_than_or_equal_to: 0)
  end

  relationships do
    belongs_to :author, Catalog.Library.Author do
      allow_nil? false
      public? true
    end

    has_many :reviews, Catalog.Library.Review do
      public? true
    end
  end

  actions do
    defaults [:destroy]

    read :read do
      primary? true
      pagination offset?: true, countable: :by_default, required?: false
    end

    create :create do
      accept [:title, :shelf, :year, :price_cents, :restricted]
      argument :author, :uuid, allow_nil?: false
      change manage_relationship(:author, type: :append_and_remove)
    end

    update :update do
      accept [:title, :shelf, :year, :price_cents, :restricted]
    end
  end

  policies do
    policy action_type(:read) do
      authorize_if actor_attribute_equals(:role, :curator)
      authorize_if expr(restricted == false)
    end

    policy action_type(:destroy) do
      authorize_if actor_attribute_equals(:role, :curator)
    end

    policy action_type([:create, :update]) do
      authorize_if always()
    end
  end

  json_api do
    type "book"
    includes [:author, :reviews]
    hide_fields [:author_id]

    routes do
      base "/books"

      get :read, primary?: true
      index :read
      post :create, relationship_arguments: [{:id, :author}]
      patch :update
      delete :destroy
    end
  end
end
