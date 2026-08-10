defmodule Orchestra.Fleet do
  @moduledoc """
  The Fleet domain: nodes, rollouts, placements, approvals and leases.
  """
  use Ash.Domain

  resources do
    resource Orchestra.Fleet.Node do
      define :register_node, action: :register, args: [:name, :region, :slots_total]
      define :get_node, action: :by_name, args: [:name], get?: true
      define :list_nodes, action: :read
    end

    resource Orchestra.Fleet.Rollout do
      define :list_rollouts, action: :read
      define :plan_rollout, action: :plan, args: [:targets]
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
