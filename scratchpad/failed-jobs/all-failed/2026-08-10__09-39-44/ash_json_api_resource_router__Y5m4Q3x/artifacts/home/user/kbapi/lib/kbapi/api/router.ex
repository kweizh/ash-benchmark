defmodule Kbapi.Api.Router do
  @moduledoc false
  use AshJsonApi.Router,
    domains: [Kbapi.Knowledge],
    prefix: "/api",
    open_api: "/open_api",
    json_schema: "/json_schema"
end
