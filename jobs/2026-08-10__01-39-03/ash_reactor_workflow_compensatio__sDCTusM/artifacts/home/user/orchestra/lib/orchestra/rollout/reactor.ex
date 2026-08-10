defmodule Orchestra.Rollout.Reactor do
  @moduledoc """
  Orchestrates a full fleet rollout: reserving capacity, obtaining approval,
  deploying with bounded parallelism, and rolling back everything already
  done if any part of the process fails.
  """
  use Ash.Reactor

  alias Orchestra.Fleet.{Lease, Node, Placement, Rollout}

  ash do
    default_domain Orchestra.Fleet
  end

  middlewares do
    middleware Orchestra.Rollout.TraceMiddleware
  end

  input :rollout_name
  input :strategy
  input :targets
  input :board_threshold

  create :create_lease, Lease, :create do
    inputs %{rollout_name: input(:rollout_name)}
    undo :always
    undo_action :release
  end

  create :create_rollout, Rollout, :create do
    inputs %{name: input(:rollout_name), strategy: input(:strategy)}
    undo :always
    undo_action :mark_failed
  end

  action :plan, Rollout, :plan do
    inputs %{targets: input(:targets)}
  end

  map :reserve_all do
    source input(:targets)
    allow_async? false
    return :create_placement

    read_one :get_node, Node, :by_name do
      inputs %{name: element(:reserve_all, [:node_name])}
      fail_on_not_found? true
    end

    update :reserve_node, Node, :reserve do
      initial result(:get_node)
      inputs %{slots: element(:reserve_all, [:slots])}
      undo :always
      undo_action :release_reservation
    end

    create :create_placement, Placement, :create do
      inputs %{
        rollout_id: result(:create_rollout, [:id]),
        node_name: element(:reserve_all, [:node_name]),
        slots: element(:reserve_all, [:slots])
      }

      wait_for :reserve_node
    end
  end

  compose :grant_approval, Orchestra.Rollout.ApprovalReactor do
    argument :rollout_id, result(:create_rollout, [:id])
    argument :total_slots, result(:plan, [:total_slots])
    argument :board_threshold, input(:board_threshold)
    wait_for :reserve_all
  end

  map :deploy_all do
    source result(:reserve_all)
    allow_async? true
    return :deploy
    wait_for :grant_approval

    step :deploy, Orchestra.Rollout.Steps.DeployNode do
      argument :placement, element(:deploy_all)
      max_retries 3
    end
  end

  update :mark_succeeded, Rollout, :mark_succeeded do
    initial result(:create_rollout)
    inputs %{deployed_node_count: result(:plan, [:target_count])}
    wait_for :deploy_all
  end

  update :release_lease, Lease, :release do
    initial result(:create_lease)
    inputs %{changeset: value(nil)}
    wait_for :mark_succeeded
  end

  step :finalize do
    argument :rollout_id, result(:create_rollout, [:id])
    argument :node_names, result(:plan, [:node_names])
    argument :total_slots, result(:plan, [:total_slots])
    argument :target_count, result(:plan, [:target_count])
    argument :approval, result(:grant_approval)
    argument :rollout_name, input(:rollout_name)
    argument :strategy, input(:strategy)
    wait_for :release_lease

    run fn args, _context ->
      level = args.approval.level

      summary =
        "Rollout #{args.rollout_name} deployed #{args.target_count} node(s) " <>
          "in #{args.strategy} mode with #{level} approval."

      {:ok,
       %{
         rollout_id: args.rollout_id,
         status: :succeeded,
         deployed_nodes: args.node_names,
         total_slots: args.total_slots,
         approval_level: level,
         summary: summary
       }}
    end
  end

  return :finalize
end
