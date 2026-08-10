defmodule Orchestra.Application do
  @moduledoc false

  use Application

  @resources [
    Orchestra.Fleet.Node,
    Orchestra.Fleet.Rollout,
    Orchestra.Fleet.Placement,
    Orchestra.Fleet.Approval,
    Orchestra.Fleet.Lease
  ]

  @impl true
  def start(_type, _args) do
    children = [
      Orchestra.Rollout.Trace
    ]

    result =
      Supervisor.start_link(children, strategy: :one_for_one, name: Orchestra.Supervisor)

    # Eagerly create the ETS tables for every resource. The ETS data layer
    # creates a table lazily on first use, but when many asynchronous steps
    # race to be the first to touch a resource the table creation can fail with
    # `:table_not_found`. Creating them up front, sequentially, removes that
    # race for the rest of the application's lifetime.
    warmup_tables()

    result
  end

  defp warmup_tables do
    Enum.each(@resources, fn resource ->
      try do
        Ash.read(Ash.Query.for_read(resource, :read))
      rescue
        _ -> :ok
      end
    end)
  end
end
