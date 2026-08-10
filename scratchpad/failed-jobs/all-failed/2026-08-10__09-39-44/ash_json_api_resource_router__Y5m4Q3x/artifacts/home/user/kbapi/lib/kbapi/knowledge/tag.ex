defmodule Kbapi.Knowledge.Tag do
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
    attribute :slug, :string, allow_nil?: false, public?: true
  end

  relationships do
    many_to_many :articles, Kbapi.Knowledge.Article do
      public? true
      through Kbapi.Knowledge.ArticleTag
      source_attribute_on_join_resource :tag_id
      destination_attribute_on_join_resource :article_id
    end
  end

  json_api do
    type "tag"

    derive_filter? false
    derive_sort? false

    routes do
      base "/tags"

      index :read, primary?: true
      get :read, primary?: true
    end
  end

  actions do
    default_accept []
    defaults [:destroy]

    read :read do
      primary? true
      skip_unknown_inputs [:filter, :sort]
    end

    create :create do
      primary? true
      accept [:name, :slug]
    end

    update :update do
      primary? true
      accept [:name, :slug]
    end
  end
end
