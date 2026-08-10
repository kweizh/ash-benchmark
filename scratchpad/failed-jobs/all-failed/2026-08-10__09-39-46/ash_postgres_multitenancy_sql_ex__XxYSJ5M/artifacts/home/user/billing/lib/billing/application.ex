defmodule Billing.Application do
  @moduledoc false
  use Application

  @impl true
  def start(_type, _args) do
    children = [
      Billing.Repo,
      Billing.Trace
    ]

    Supervisor.start_link(children, strategy: :one_for_one, name: Billing.Supervisor)
  end
end
