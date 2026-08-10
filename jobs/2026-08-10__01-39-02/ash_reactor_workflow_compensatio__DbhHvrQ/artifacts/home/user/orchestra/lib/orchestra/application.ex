defmodule Orchestra.Application do
  @moduledoc false

  use Application

  @impl true
  def start(_type, _args) do
    children = [
      {Orchestra.Rollout.Trace, []}
    ]

    Supervisor.start_link(children, strategy: :one_for_one, name: Orchestra.Supervisor)
  end
end
