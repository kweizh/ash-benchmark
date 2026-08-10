defmodule Kbapi.Knowledge do
  use Ash.Domain,
    otp_app: :kbapi,
    extensions: [AshJsonApi.Domain]

  json_api do
    prefix "/api"
    authorize? true
    require_type_on_create? true

    routes do
      base_route "/feed", Kbapi.Knowledge.Article do
        index :feed, derive_sort?: false, derive_filter?: false
      end

      base_route "/moderation/comments", Kbapi.Knowledge.Comment do
        index :pending, route: "/pending"
        patch :approve, route: "/:id/approve"
      end
    end
  end

  resources do
    resource Kbapi.Knowledge.Author
    resource Kbapi.Knowledge.Article
    resource Kbapi.Knowledge.Tag
    resource Kbapi.Knowledge.ArticleTag
    resource Kbapi.Knowledge.Comment
  end
end
