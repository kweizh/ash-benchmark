defmodule Orchestra.Rollout.Steps.DeployNode do
  use Reactor.Step

  @impl true
  def run(arguments, _context, _options) do
    rollout_id = arguments[:rollout_id]
    target = arguments[:target]
    node_name = target.node_name

    # Trace: {:deploy_enter, name}
    Orchestra.Rollout.Trace.record(:deploy_enter, node_name)

    # Every deployment attempt takes at least 50 ms of wall-clock time
    Process.sleep(50)

    # Fetch the Placement record
    placement =
      Orchestra.Fleet.list_placements!()
      |> Enum.find(fn p -> p.rollout_id == rollout_id and p.node_name == node_name end)

    # Raise attempts by one and set status to :deploying
    placement =
      placement
      |> Ash.Changeset.for_update(:update, %{
        attempts: placement.attempts + 1,
        status: :deploying
      })
      |> Ash.update!()

    # Fetch the Node record
    node = Orchestra.Fleet.get_node!(node_name)

    # Check if the attempt fails
    if node.deploy_failures_remaining > 0 do
      # Reduce deploy_failures_remaining by one
      _node =
        node
        |> Ash.Changeset.for_update(:update, %{
          deploy_failures_remaining: node.deploy_failures_remaining - 1
        })
        |> Ash.update!()

      # Trace: {:deploy_exit, name}
      Orchestra.Rollout.Trace.record(:deploy_exit, node_name)

      # Return failure
      {:error, {:deploy_failed, node_name}}
    else
      # Successful attempt: set status to :deployed and node state to :live
      _placement =
        placement
        |> Ash.Changeset.for_update(:update, %{status: :deployed})
        |> Ash.update!()

      _node =
        node
        |> Ash.Changeset.for_update(:update, %{state: :live})
        |> Ash.update!()

      # Trace: {:deploy_exit, name}
      Orchestra.Rollout.Trace.record(:deploy_exit, node_name)

      {:ok, node_name}
    end
  end

  @impl true
  def compensate(reason, arguments, _context, _options) do
    rollout_id = arguments[:rollout_id]
    target = arguments[:target]
    node_name = target.node_name

    # Trace: {:deploy_compensate, name}
    Orchestra.Rollout.Trace.record(:deploy_compensate, node_name)

    # Fetch the Placement record
    placement =
      Orchestra.Fleet.list_placements!()
      |> Enum.find(fn p -> p.rollout_id == rollout_id and p.node_name == node_name end)

    # Raise compensations by one and status returns to :reserved
    placement =
      placement
      |> Ash.Changeset.for_update(:update, %{
        compensations: placement.compensations + 1,
        status: :reserved
      })
      |> Ash.update!()

    # Check if we can retry
    if placement.attempts < 4 do
      :retry
    else
      {:error, reason}
    end
  end

  @impl true
  def undo(value, arguments, _context, _options) do
    # value is what run/3 returned on success, which is node_name!
    node_name = value
    rollout_id = arguments[:rollout_id]

    # Trace: {:deploy_undo, name}
    Orchestra.Rollout.Trace.record(:deploy_undo, node_name)

    # Fetch the Placement record
    placement =
      Orchestra.Fleet.list_placements!()
      |> Enum.find(fn p -> p.rollout_id == rollout_id and p.node_name == node_name end)

    # Raise undos by one and status is set to :released
    _placement =
      placement
      |> Ash.Changeset.for_update(:update, %{
        undos: placement.undos + 1,
        status: :released
      })
      |> Ash.update!()

    :ok
  end
end
