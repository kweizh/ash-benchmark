defmodule Catalog.JsonApiRouter do
  use AshJsonApi.Router,
    domains: [Catalog.Library]
end
