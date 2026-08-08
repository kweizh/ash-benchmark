defmodule Catalog.Library do
  use Ash.Domain,
    extensions: [AshJsonApi.Domain],
    otp_app: :catalog

  json_api do
    prefix "/api/json"

    routes do
      route Catalog.Library.Book, :get, "/reports/shelf_summary", :shelf_summary,
        wrap_in_result?: true
    end
  end

  resources do
    resource Catalog.Library.Author
    resource Catalog.Library.Book
    resource Catalog.Library.Review
  end
end
