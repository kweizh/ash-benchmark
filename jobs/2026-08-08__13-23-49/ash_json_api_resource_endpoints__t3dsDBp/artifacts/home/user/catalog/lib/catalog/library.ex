defmodule Catalog.Library do
  use Ash.Domain,
    otp_app: :catalog,
    extensions: [AshJsonApi.Domain]

  resources do
    resource Catalog.Library.Author
    resource Catalog.Library.Book
    resource Catalog.Library.Review
  end

  json_api do
    # Global JSON:API configuration
    # By default, authorize? is true.
  end
end
