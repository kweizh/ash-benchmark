defmodule Orchestra.Fleet do
  use Ash.Domain

  resources do
    resource Orchestra.Fleet.Node do
      define :register_node, action: :create, args: [:name, :region, :slots_total]
      define :get_node, action: :get_by_name, args: [:name]
      define :list_nodes, action: :read
    end

    resource Orchestra.Fleet.Rollout do
      define :list_rollouts, action: :read
      define :plan_rollout, action: :plan_rollout, args: [:targets]
    end

    resource Orchestra.Fleet.Placement do
      define :list_placements, action: :read
    end

    resource Orchestra.Fleet.Approval do
      define :list_approvals, action: :read
    end

    resource Orchestra.Fleet.Lease do
      define :list_leases, action: :read
    end
  end
end
