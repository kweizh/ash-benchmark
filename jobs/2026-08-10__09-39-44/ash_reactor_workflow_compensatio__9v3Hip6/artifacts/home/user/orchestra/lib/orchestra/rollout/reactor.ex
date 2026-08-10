defmodule Orchestra.Rollout.Reactor do
  @moduledoc """
  The end-to-end rollout orchestration graph.

  Reserves capacity on every target node, obtains an approval, deploys to the
  nodes with bounded parallelism, and — if anything goes wrong — reverses
  everything that had already succeeded via Reactor's undo machinery.
  """

  use Ash.Reactor

  middlewares do
    middleware Orchestra.Rollout.Middleware
  end

  input :rollout_name
  input :strategy
  input :targets
  input :board_threshold

  # Compute the rollout plan (total slots, node names, target count) and
  # validate the targets up front. This is the generic-action step.
  action :plan, Orchestra.Fleet.Rollout, :plan_rollout do
    inputs %{targets: input(:targets)}
  end

  # The lease is held for the whole run and released come what may.
  create :create_lease, Orchestra.Fleet.Lease, :create do
    inputs %{rollout_name: input(:rollout_name)}
    undo :always
    undo_action :release
  end

  # The rollout record. On success it is marked :succeeded; on failure the
  # undo action marks it :rolled_back.
  create :create_rollout, Orchestra.Fleet.Rollout, :create do
    inputs %{
      name: input(:rollout_name),
      strategy: input(:strategy)
    }

    undo :always
    undo_action :mark_rolled_back
  end

  # Obtain the approval. This is the compose step embedding the independently
  # runnable `ApprovalReactor`.
  compose :approve, Orchestra.Rollout.ApprovalReactor do
    argument :rollout_id, result(:create_rollout, [:id])
    argument :total_slots, result(:plan, [:total_slots])
    argument :board_threshold, input(:board_threshold)
  end

  # Reserve capacity on every target node. This is a map step over the targets.
  map :reserve do
    source input(:targets)
    allow_async? true
    wait_for [:create_rollout]

    read_one :read_node, Orchestra.Fleet.Node, :get_by_name do
      inputs %{node_name: element(:reserve, [:node_name])}
      fail_on_not_found? true
    end

    step :check_capacity do
      argument :node, result(:read_node)
      argument :target, element(:reserve)

      run fn %{node: node, target: target}, _ ->
        slots = Map.fetch!(target, :slots)

        if node.slots_used + slots > node.slots_total do
          {:error, :insufficient_capacity}
        else
          {:ok, node.slots_used + slots}
        end
      end
    end

    create :create_placement, Orchestra.Fleet.Placement, :create do
      inputs %{
        rollout_id: result(:create_rollout, [:id]),
        node_name: element(:reserve, [:node_name]),
        slots: element(:reserve, [:slots])
      }

      wait_for [:check_capacity]
    end

    update :update_node, Orchestra.Fleet.Node, :reserve do
      initial result(:read_node)
      inputs %{slots_used: result(:check_capacity)}
      undo :always
      undo_action :release_reservation
      wait_for [:check_capacity, :create_placement]
    end

    return :update_node
  end

  # Deploy to every target node with bounded parallelism (batch size two).
  # This is a second map step over the targets.
  map :deploy do
    source input(:targets)
    allow_async? true
    batch_size 2
    wait_for [:reserve, :approve]

    step :deploy_node, Orchestra.Rollout.Steps.DeployNode do
      argument :target, element(:deploy)
      argument :rollout_id, result(:create_rollout, [:id])
      max_retries 3
    end

    return :deploy_node
  end

  # On success, mark the rollout as succeeded with its deployed node count.
  update :mark_succeeded, Orchestra.Fleet.Rollout, :mark_succeeded do
    initial result(:create_rollout)
    inputs %{deployed_node_count: result(:plan, [:target_count])}
    wait_for [:deploy]
  end

  # On success, release the lease.
  update :release_lease, Orchestra.Fleet.Lease, :release do
    initial result(:create_lease)
    wait_for [:deploy]
  end

  step :build_result do
    argument :rollout_id, result(:create_rollout, [:id])
    argument :node_names, result(:plan, [:node_names])
    argument :total_slots, result(:plan, [:total_slots])
    argument :approval_level, result(:approve, [:level])
    argument :target_count, result(:plan, [:target_count])
    argument :rollout_name, input(:rollout_name)
    argument :strategy, input(:strategy)
    wait_for [:deploy, :mark_succeeded, :release_lease]

    run fn args, _ ->
      summary =
        "Rollout #{args.rollout_name} deployed #{args.target_count} node(s) in #{args.strategy} mode with #{args.approval_level} approval."

      {:ok,
       %{
         rollout_id: args.rollout_id,
         status: :succeeded,
         deployed_nodes: args.node_names,
         total_slots: args.total_slots,
         approval_level: args.approval_level,
         summary: summary
       }}
    end
  end

  return :build_result
end
