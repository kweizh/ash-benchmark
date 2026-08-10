defmodule Kbapi.Knowledge.Tag do
  use Ash.Resource,
    otp_app: :kbapi,
    domain: Kbapi.Knowledge,
    data_layer: Ash.DataLayer.Ets

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

  actions do
    default_accept []
    defaults [:read, :destroy]

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
