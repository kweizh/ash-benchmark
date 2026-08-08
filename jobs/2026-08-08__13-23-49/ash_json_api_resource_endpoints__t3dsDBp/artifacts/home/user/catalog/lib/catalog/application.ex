defmodule Catalog.Application do
  @moduledoc false
  use Application

  @impl true
  def start(_type, _args) do
    children = [
      {Bandit, plug: Catalog.Router, port: 4001, ip: {127, 0, 0, 1}}
    ]

    Supervisor.start_link(children, strategy: :one_for_one, name: Catalog.Supervisor)
  end
end
