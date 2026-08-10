defmodule Orchestra.Rollout.Steps.DeployNode do
  @moduledoc false

  use Reactor.Step

  alias Ash.Changeset
  alias Orchestra.Fleet.{Node, Placement}
  alias Orchestra.Rollout.Trace

  import Ash.Query

  @deploy_duration_ms 50

  @impl true
  def run(arguments, _context, _opts) do
    target = Map.fetch!(arguments, :target)
    rollout_id = Map.fetch!(arguments, :rollout_id)
    node_name = Map.fetch!(target, :node_name)

    with {:ok, placement} <- get_placement(rollout_id, node_name),
         {:ok, node} <- get_node(node_name) do
      Trace.record({:deploy_enter, node_name})

      {:ok, deploying_placement} =
        update_placement(placement, %{
          attempts: placement.attempts + 1,
          status: :deploying
        })

      Process.sleep(@deploy_duration_ms)

      Trace.record({:deploy_exit, node_name})

      if node.deploy_failures_remaining > 0 do
        {:ok, _} =
          update_node(node, %{
            deploy_failures_remaining: node.deploy_failures_remaining - 1
          })

        {:error, :deploy_failed}
      else
        {:ok, _} = update_placement(deploying_placement, %{status: :deployed})
        {:ok, _} = update_node(node, %{state: :live})
        {:ok, %{node_name: node_name, deployed: true}}
      end
    end
  end

  @impl true
  def compensate(_reason, arguments, _context, _opts) do
    target = Map.fetch!(arguments, :target)
    rollout_id = Map.fetch!(arguments, :rollout_id)
    node_name = Map.fetch!(target, :node_name)

    case get_placement(rollout_id, node_name) do
      {:ok, placement} ->
        {:ok, _} =
          update_placement(placement, %{
            compensations: placement.compensations + 1,
            status: :reserved
          })

        Trace.record({:deploy_compensate, node_name})
        :retry

      _ ->
        Trace.record({:deploy_compensate, node_name})
        :retry
    end
  end

  @impl true
  def undo(_value, arguments, _context, _opts) do
    target = Map.fetch!(arguments, :target)
    rollout_id = Map.fetch!(arguments, :rollout_id)
    node_name = Map.fetch!(target, :node_name)

    case get_placement(rollout_id, node_name) do
      {:ok, placement} ->
        {:ok, _} =
          update_placement(placement, %{
            undos: placement.undos + 1,
            status: :released
          })

        Trace.record({:deploy_undo, node_name})
        :ok

      _ ->
        Trace.record({:deploy_undo, node_name})
        :ok
    end
  end

  defp get_placement(rollout_id, node_name) do
    Placement
    |> Ash.Query.for_read(:read)
    |> filter(rollout_id == ^rollout_id and node_name == ^node_name)
    |> Ash.read()
    |> case do
      {:ok, [placement | _]} -> {:ok, placement}
      {:ok, []} -> {:error, :placement_not_found}
      {:error, _} = error -> error
    end
  end

  defp get_node(node_name) do
    Node
    |> Ash.Query.for_read(:read)
    |> filter(name == ^node_name)
    |> Ash.read_one()
  end

  defp update_placement(placement, attrs) do
    placement
    |> Changeset.for_update(:update, attrs)
    |> Ash.update()
  end

  defp update_node(node, attrs) do
    node
    |> Changeset.for_update(:update, attrs)
    |> Ash.update()
  end
end
