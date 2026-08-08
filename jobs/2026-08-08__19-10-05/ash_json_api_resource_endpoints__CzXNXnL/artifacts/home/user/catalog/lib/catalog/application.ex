defmodule Catalog.Application do
  @moduledoc false
  use Application

  @impl true
  def start(_type, _args) do
    children = [
      {Bandit, scheme: :http, port: 4001, plug: Catalog.JsonApiRouter}
    ]

    Supervisor.start_link(children, strategy: :one_for_one, name: Catalog.Supervisor)
  end
end
