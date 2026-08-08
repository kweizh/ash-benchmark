defmodule Catalog.Library.Book do
  use Ash.Resource,
    domain: Catalog.Library,
    data_layer: Ash.DataLayer.Ets,
    extensions: [AshJsonApi.Resource],
    authorizers: [Ash.Policy.Authorizer]

  ets do
    private? false
  end

  json_api do
    type "book"

    includes [
      author: [],
      reviews: []
    ]

    routes do
      base "/books"

      index :read
      get :read
      post :create
      patch :update
      delete :destroy
    end
  end

  attributes do
    uuid_primary_key :id

    attribute :title, :string do
      public? true
      allow_nil? false
      constraints min_length: 1
    end

    attribute :shelf, :string do
      public? true
      allow_nil? false
      constraints min_length: 1
    end

    attribute :year, :integer do
      public? true
      allow_nil? false
      constraints min: 1450, max: 2100
    end

    attribute :price_cents, :integer do
      public? true
      allow_nil? false
      constraints min: 0
    end

    attribute :restricted, :boolean do
      public? true
      allow_nil? false
      default false
    end
  end

  relationships do
    belongs_to :author, Catalog.Library.Author do
      public? true
      allow_nil? false
      attribute_writable? true
    end

    has_many :reviews, Catalog.Library.Review do
      public? true
    end
  end

  actions do
    defaults [:destroy]

    read :read do
      primary? true
      pagination offset?: true, default_limit: 20, countable: true
    end

    create :create do
      primary? true
      accept [:title, :shelf, :year, :price_cents, :restricted]
    end

    update :update do
      primary? true
      accept [:title, :shelf, :year, :price_cents, :restricted]
      require_atomic? false
    end

    action :shelf_summary, :map do
      argument :shelf, :string, allow_nil?: false

      run fn input, _context ->
        shelf = input.arguments.shelf

        books =
          Catalog.Library.Book
          |> Ash.Query.filter(shelf: shelf)
          |> Ash.read!(authorize?: false)

        book_ids = Enum.map(books, & &1.id)

        review_count =
          if book_ids != [] do
            Catalog.Library.Review
            |> Ash.Query.filter(book_id: [in: book_ids])
            |> Ash.read!(authorize?: false)
            |> Enum.count()
          else
            0
          end

        total_price_cents =
          books
          |> Enum.map(& &1.price_cents)
          |> Enum.sum()

        {:ok,
         %{
           shelf: shelf,
           book_count: Enum.count(books),
           review_count: review_count,
           total_price_cents: total_price_cents
         }}
      end
    end
  end

  policies do
    policy action_type(:read) do
      authorize_if always()
    end

    policy action_type([:create, :update]) do
      authorize_if always()
    end

    policy action_type(:destroy) do
      authorize_if actor_attribute_equals(:role, :curator)
    end

    policy action_type(:action) do
      authorize_if always()
    end
  end
end
