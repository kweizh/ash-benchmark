defmodule Kbapi.Knowledge.ArticleTag do
  use Ash.Resource,
    otp_app: :kbapi,
    domain: Kbapi.Knowledge,
    data_layer: Ash.DataLayer.Ets

  ets do
    private? true
  end

  relationships do
    belongs_to :article, Kbapi.Knowledge.Article do
      primary_key? true
      allow_nil? false
      attribute_writable? true
    end

    belongs_to :tag, Kbapi.Knowledge.Tag do
      primary_key? true
      allow_nil? false
      attribute_writable? true
    end
  end

  actions do
    default_accept []
    defaults [:read, :destroy]

    create :create do
      primary? true
      accept [:article_id, :tag_id]
    end
  end
end
