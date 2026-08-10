defmodule Logistics.Application do
  @moduledoc false

  use Application

  @impl true
  def start(_type, _args) do
    children = [
      Logistics.Repo
    ]

    Supervisor.start_link(children, strategy: :one_for_one, name: Logistics.Supervisor)
  end
end
