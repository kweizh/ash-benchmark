defmodule Orchestra.Rollout.Steps.DeployNode do
  @moduledoc """
  A custom `Reactor.Step` responsible for deploying a single target node.

  This is the one place in the workflow that is allowed to call Ash directly
  (rather than going through `Ash.Reactor`'s resource-action step types),
  because the retry/compensate/undo semantics required here (bounded
  concurrency, transient-failure retries, per-attempt bookkeeping) don't map
  onto the standard action step types.
  """
  use Reactor.Step

  alias Orchestra.Fleet
  alias Orchestra.Fleet.Placement
  alias Orchestra.Rollout.{Semaphore, Trace}

  defmodule DeployFailed do
    @moduledoc false
    defexception [:node_name, :placement_id]

    @impl true
    def message(%{node_name: node_name}), do: "deployment failed for node #{node_name}"
  end

  @impl true
  def run(%{placement: placement}, _context, _options) do
    node_name = placement.node_name
    placement_id = placement.id

    :ok = Semaphore.acquire()

    try do
      Trace.record({:deploy_enter, node_name})

      Placement
      |> Ash.get!(placement_id)
      |> Ash.Changeset.for_update(:begin_attempt, %{})
      |> Ash.update!()

      Process.sleep(50)

      node = Fleet.get_node!(node_name)

      result =
        if node.deploy_failures_remaining > 0 do
          node
          |> Ash.Changeset.for_update(:consume_failure, %{})
          |> Ash.update!()

          {:error, %DeployFailed{node_name: node_name, placement_id: placement_id}}
        else
          node
          |> Ash.Changeset.for_update(:go_live, %{})
          |> Ash.update!()

          Placement
          |> Ash.get!(placement_id)
          |> Ash.Changeset.for_update(:mark_deployed, %{})
          |> Ash.update!()

          {:ok, %{placement_id: placement_id, node_name: node_name}}
        end

      Trace.record({:deploy_exit, node_name})
      result
    after
      Semaphore.release()
    end
  end

  @impl true
  def compensate(_reason, %{placement: placement}, _context, _options) do
    Placement
    |> Ash.get!(placement.id)
    |> Ash.Changeset.for_update(:mark_compensated, %{})
    |> Ash.update!()

    Trace.record({:deploy_compensate, placement.node_name})
    :retry
  end

  @impl true
  def undo(_value, %{placement: placement}, _context, _options) do
    Placement
    |> Ash.get!(placement.id)
    |> Ash.Changeset.for_update(:mark_released, %{})
    |> Ash.update!()

    Trace.record({:deploy_undo, placement.node_name})
    :ok
  end
end
