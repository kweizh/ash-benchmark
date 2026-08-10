defmodule Kbapi.Knowledge.Article do
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
    attribute :title, :string, allow_nil?: false, public?: true, constraints: [min_length: 3]
    attribute :slug, :string, allow_nil?: false, public?: true
    attribute :body, :string, public?: true

    attribute :status, :atom,
      public?: true,
      default: :draft,
      constraints: [one_of: [:draft, :published, :archived]]

    attribute :rank, :integer, public?: true, default: 0
    attribute :word_count, :integer, public?: true, default: 0
  end

  relationships do
    belongs_to :author, Kbapi.Knowledge.Author do
      public? true
      allow_nil? false
      attribute_writable? true
    end

    has_many :comments, Kbapi.Knowledge.Comment do
      public? true
    end

    many_to_many :tags, Kbapi.Knowledge.Tag do
      public? true
      through Kbapi.Knowledge.ArticleTag
      source_attribute_on_join_resource :article_id
      destination_attribute_on_join_resource :tag_id
    end
  end

  aggregates do
    count :comment_count, :comments do
      public? true
    end
  end

  json_api do
    type "article"

    default_fields [:title, :slug, :body, :status, :rank, :word_count, :author_id]

    always_include_linkage [:author]

    includes [
      author: [articles: []],
      tags: [],
      comments: []
    ]

    routes do
      base "/articles"

      index :read, primary?: true
      get :read, primary?: true
      post :create
      patch :update, relationship_arguments: [:tags]
      delete :destroy
      patch :publish, route: "/:id/publish"
      related :comments, :read, primary?: true
      relationship :tags, :read, primary?: true
      post_to_relationship :tags
      patch_relationship :tags
      delete_from_relationship :tags
      route :post, "/reindex", :reindex
      route :get, "/tally/:status", :tally, wrap_in_result?: true
    end
  end

  policies do
    policy action_type(:read) do
      authorize_if always()
    end

    policy action(:tally) do
      authorize_if always()
    end

    policy action(:reindex) do
      authorize_if expr(actor.role == :admin)
    end

    policy action_type([:create, :update, :destroy]) do
      authorize_if expr(actor.role in [:editor, :admin])
    end
  end

  actions do
    default_accept []
    defaults [:destroy]

    read :read do
      primary? true
      pagination offset?: true, default_limit: 2, countable: false, required?: false
    end

    read :feed do
      pagination keyset?: true, offset?: false, default_limit: 2, countable: false, required?: true
      skip_unknown_inputs [:sort, :filter]

      prepare fn query, _context ->
        Ash.Query.sort(query, rank: :desc, id: :asc)
      end
    end

    create :create do
      primary? true
      accept [:title, :slug, :body, :status, :rank, :word_count, :author_id]
    end

    update :update do
      primary? true
      accept [:title, :body, :status, :rank, :word_count]

      argument :tags, {:array, :map} do
        public? true
      end

      change manage_relationship(:tags, type: :append_and_remove)
    end

    update :publish do
      accept []
      require_atomic? false
      validate {Kbapi.Knowledge.Article.Validations.NotArchived, []}
      change set_attribute(:status, :published)
    end

    action :reindex, :map do
      run fn _input, _context ->
        articles = Ash.read!(Kbapi.Knowledge.Article, authorize?: false)

        {:ok,
         %{
           indexed: length(articles),
           published: Enum.count(articles, &(&1.status == :published)),
           words: Enum.sum(Enum.map(articles, &(&1.word_count || 0)))
         }}
      end
    end

    action :tally, :integer do
      argument :status, :atom do
        public? true
        constraints [one_of: [:draft, :published, :archived]]
      end

      run fn input, _context ->
        articles = Ash.read!(Kbapi.Knowledge.Article, authorize?: false)
        count = Enum.count(articles, &(&1.status == input.arguments.status))
        {:ok, count}
      end
    end
  end
end
