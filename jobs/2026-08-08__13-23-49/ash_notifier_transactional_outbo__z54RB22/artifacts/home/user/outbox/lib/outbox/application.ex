defmodule Outbox.Application do
  @moduledoc false

  use Application

  @impl true
  def start(_type, _args) do
    children = [
      Outbox.Eventing.SequenceServer,
      Outbox.Eventing.Dispatcher
    ]

    Supervisor.start_link(children, strategy: :one_for_one, name: Outbox.Supervisor)
  end
end
