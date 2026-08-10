defmodule Orchestra.Rollout.Reactor do
  use Ash.Reactor

  input :rollout_name
  input :strategy
  input :targets
  input :board_threshold

  middlewares do
    middleware Orchestra.Rollout.Middleware
  end

  create :create_lease, Orchestra.Fleet.Lease, :create do
    inputs %{
      rollout_name: input(:rollout_name),
      status: value(:held)
    }
    undo :always
    undo_action :release
  end

  create :create_rollout, Orchestra.Fleet.Rollout, :create do
    inputs %{
      name: input(:rollout_name),
      strategy: input(:strategy),
      status: value(:running)
    }
    undo :always
    undo_action :rollback
  end

  action :plan, Orchestra.Fleet.Rollout, :plan_rollout do
    inputs %{
      targets: input(:targets)
    }
  end

  compose :approval, Orchestra.Rollout.ApprovalReactor do
    argument :rollout_id, result(:create_rollout, [:id])
    argument :total_slots, result(:plan, [:total_slots])
    argument :board_threshold, input(:board_threshold)
  end

  map :reserve_all do
    source input(:targets)
    return :create_placement

    read_one :get_node, Orchestra.Fleet.Node, :get_by_name do
      inputs %{name: element(:reserve_all, [:node_name])}
    end

    step :validate_and_calc do
      argument :node, result(:get_node)
      argument :target, element(:reserve_all)

      run fn %{node: node, target: target}, _ ->
        slots = target.slots
        if is_nil(node) do
          {:error, %Ash.Error.Invalid{errors: [
            %Ash.Error.Action.InvalidArgument{field: :targets, message: "Node not found", value: target.node_name}
          ]}}
        else
          new_slots_used = node.slots_used + slots
          if new_slots_used > node.slots_total do
            {:error, %Ash.Error.Invalid{errors: [
              %Ash.Error.Action.InvalidArgument{field: :targets, message: "Insufficient slots", value: target.node_name}
            ]}}
          else
            {:ok, %{
              slots_used: new_slots_used,
              state: :reserved
            }}
          end
        end
      end
    end

    update :update_node, Orchestra.Fleet.Node, :update do
      initial result(:get_node)
      inputs %{
        slots_used: result(:validate_and_calc, [:slots_used]),
        state: result(:validate_and_calc, [:state])
      }
      undo :always
      undo_action :undo_reserve
    end

    create :create_placement, Orchestra.Fleet.Placement, :create do
      inputs %{
        rollout_id: result(:create_rollout, [:id]),
        node_name: element(:reserve_all, [:node_name]),
        slots: element(:reserve_all, [:slots]),
        status: value(:reserved)
      }
      wait_for [:update_node]
    end
  end

  map :deploy_all do
    source input(:targets)
    batch_size 2
    allow_async? true
    wait_for [:reserve_all, :approval]
    return :deploy_node

    step :deploy_node, Orchestra.Rollout.Steps.DeployNode do
      argument :target, element(:deploy_all)
      argument :rollout_id, result(:create_rollout, [:id])
    end
  end

  update :complete_rollout, Orchestra.Fleet.Rollout, :update do
    initial result(:create_rollout)
    inputs %{
      status: value(:succeeded),
      deployed_node_count: result(:plan, [:target_count])
    }
    wait_for [:deploy_all]
  end

  update :release_lease_success, Orchestra.Fleet.Lease, :release do
    initial result(:create_lease)
    wait_for [:deploy_all]
  end

  step :build_result do
    argument :rollout, result(:create_rollout)
    argument :plan, result(:plan)
    argument :approval, result(:approval)
    wait_for [:complete_rollout, :release_lease_success]

    run fn %{rollout: rollout, plan: plan, approval: approval}, _ ->
      target_count = plan.target_count
      approval_level = approval.level
      rollout_name = rollout.name
      strategy = rollout.strategy

      summary = "Rollout #{rollout_name} deployed #{target_count} node(s) in #{strategy} mode with #{approval_level} approval."

      {:ok, %{
        rollout_id: rollout.id,
        status: :succeeded,
        deployed_nodes: plan.node_names,
        total_slots: plan.total_slots,
        approval_level: approval.level,
        summary: summary
      }}
    end
  end

  return :build_result
end
