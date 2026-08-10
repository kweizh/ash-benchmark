defmodule Kbapi.Knowledge.Article do
  use Ash.Resource,
    otp_app: :kbapi,
    domain: Kbapi.Knowledge,
    data_layer: Ash.DataLayer.Ets

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

  actions do
    default_accept []
    defaults [:read, :destroy]

    create :create do
      primary? true
      accept [:title, :slug, :body, :status, :rank, :word_count, :author_id]
    end

    update :update do
      primary? true
      accept [:title, :body, :status, :rank, :word_count]
    end
  end
end
