defmodule Kbapi.Knowledge do
  use Ash.Domain, otp_app: :kbapi

  resources do
    resource Kbapi.Knowledge.Author
    resource Kbapi.Knowledge.Article
    resource Kbapi.Knowledge.Tag
    resource Kbapi.Knowledge.ArticleTag
    resource Kbapi.Knowledge.Comment
  end
end
