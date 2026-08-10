defmodule Scenario do
  @resources [
    Orchestra.Fleet.Node,
    Orchestra.Fleet.Rollout,
    Orchestra.Fleet.Placement,
    Orchestra.Fleet.Approval,
    Orchestra.Fleet.Lease
  ]

  def reset!, do: Orchestra.Rollout.Trace.reset()

  def flush! do
    for r <- @resources, do: Ash.DataLayer.Ets.stop(r)

    for r <- @resources do
      Ash.read(Ash.Query.for_read(r, :read))
    end

    :ok
  end

  def register!(name, region, slots_total, opts \\ []) do
    Orchestra.Fleet.register_node!(name, region, slots_total, Enum.into(opts, %{}))
  end

  def targets(names_slots) do
    Enum.map(names_slots, fn {n, s} -> %{node_name: n, slots: s} end)
  end

  def run(inputs) do
    Orchestra.Rollout.Trace.reset()
    Reactor.run(Orchestra.Rollout.Reactor, inputs)
  end

  def nodes, do: Orchestra.Fleet.list_nodes!()
  def rollouts, do: Orchestra.Fleet.list_rollouts!()
  def placements, do: Orchestra.Fleet.list_placements!()
  def approvals, do: Orchestra.Fleet.list_approvals!()
  def leases, do: Orchestra.Fleet.list_leases!()
end

defmodule HappyPath do
  def run do
    Scenario.reset!()
    Scenario.flush!()
    Scenario.register!("n1", :us_east, 10)
    Scenario.register!("n2", :eu_west, 10)
    Scenario.register!("n3", :ap_south, 10)

    inputs = %{
      rollout_name: "rollout-1",
      strategy: :canary,
      targets: Scenario.targets([{"n1", 2}, {"n2", 3}, {"n3", 1}]),
      board_threshold: 100
    }

    {:ok, result} = Scenario.run(inputs)

    rollout = hd(Scenario.rollouts())
    lease = hd(Scenario.leases())
    approval = hd(Scenario.approvals())
    placements = Scenario.placements()
    nodes = Scenario.nodes()

    true = result.status == :succeeded
    true = result.deployed_nodes == ["n1", "n2", "n3"]
    true = result.total_slots == 6
    true = result.approval_level == :auto
    true = result.summary == "Rollout rollout-1 deployed 3 node(s) in canary mode with auto approval."
    true = rollout.status == :succeeded
    true = rollout.deployed_node_count == 3
    true = lease.status == :released
    true = approval.status == :granted
    true = approval.level == :auto
    true = approval.slots == 6
    true = length(placements) == 3
    true = Enum.all?(placements, &(&1.status == :deployed and &1.attempts == 1 and &1.undos == 0))
    true = Enum.all?(nodes, &(&1.state == :live))

    IO.puts("HAPPY PATH OK")
  end
end

defmodule FailurePath do
  def run do
    Scenario.reset!()
    Scenario.flush!()
    Scenario.register!("n1", :us_east, 10)
    Scenario.register!("n2", :eu_west, 10)
    Scenario.register!("n3", :ap_south, 10, deploy_failures_remaining: 4)

    inputs = %{
      rollout_name: "rollout-2",
      strategy: :blast,
      targets: Scenario.targets([{"n1", 2}, {"n2", 3}, {"n3", 1}]),
      board_threshold: 100
    }

    {:error, _} = Scenario.run(inputs)

    rollout = hd(Scenario.rollouts())
    lease = hd(Scenario.leases())
    approval = hd(Scenario.approvals())
    placements = Scenario.placements()
    nodes = Scenario.nodes()

    by_name = Map.new(placements, &{&1.node_name, &1})
    n1 = by_name["n1"]
    n2 = by_name["n2"]
    n3 = by_name["n3"]

    true = n1.undos == 1
    true = n1.status == :released
    true = n1.attempts == 1
    true = n2.undos == 1
    true = n2.status == :released
    true = n2.attempts == 1
    true = n3.attempts == 4
    true = n3.compensations == 4
    true = n3.undos == 0
    true = n3.status == :reserved

    true = rollout.status == :rolled_back
    true = rollout.deployed_node_count == 0
    true = lease.status == :released
    true = approval.status == :revoked

    node_map = Map.new(nodes, &{&1.name, &1})
    true = Enum.all?(Map.values(node_map), &(&1.slots_used == 0 and &1.state == :idle))

    trace = Orchestra.Rollout.Trace.entries()
    events = Enum.map(trace, &elem(&1, 0))
    true = :reactor_error in events
    true = :deploy_compensate in events
    true = :deploy_undo in events
    true = :reserve_undo in events
    true = :reactor_init in events
    true = Enum.count(trace, &(&1 == {:deploy_compensate, "n3"})) == 4
    true = Enum.count(trace, &(&1 == {:deploy_enter, "n3"})) == 4
    true = Enum.count(trace, &(&1 == {:deploy_exit, "n3"})) == 4
    true = Enum.count(trace, &(&1 == {:deploy_undo, "n1"})) == 1
    true = Enum.count(trace, &(&1 == {:reserve_undo, "n1"})) == 1
    true = Enum.count(trace, &(&1 == {:reserve_undo, "n3"})) == 1

    IO.puts("FAILURE PATH OK")
  end
end

defmodule RetrySucceeds do
  def run do
    Scenario.reset!()
    Scenario.flush!()
    Scenario.register!("r1", :us_east, 10, deploy_failures_remaining: 3)

    inputs = %{
      rollout_name: "rollout-r",
      strategy: :canary,
      targets: Scenario.targets([{"r1", 2}]),
      board_threshold: 100
    }

    {:ok, result} = Scenario.run(inputs)

    [placement] = Scenario.placements()
    true = placement.attempts == 4
    true = placement.compensations == 3
    true = placement.undos == 0
    true = placement.status == :deployed
    true = result.deployed_nodes == ["r1"]

    [node] = Scenario.nodes()
    true = node.deploy_failures_remaining == 0
    true = node.state == :live

    IO.puts("RETRY SUCCEEDS OK")
  end
end

defmodule NodeNotFound do
  def run do
    Scenario.reset!()
    Scenario.flush!()
    Scenario.register!("x1", :us_east, 10)

    inputs = %{
      rollout_name: "rollout-nf",
      strategy: :canary,
      targets: Scenario.targets([{"x1", 1}, {"ghost", 1}]),
      board_threshold: 100
    }

    {:error, _} = Scenario.run(inputs)

    # No placements should have been committed for the run that failed? They may
    # be created for x1 before ghost fails. The run must fail.
    true = Scenario.rollouts() |> hd() |> Map.get(:status) == :rolled_back
    IO.puts("NODE NOT FOUND OK")
  end
end

defmodule InsufficientCapacity do
  def run do
    Scenario.reset!()
    Scenario.flush!()
    Scenario.register!("c1", :us_east, 5)

    inputs = %{
      rollout_name: "rollout-cap",
      strategy: :canary,
      targets: Scenario.targets([{"c1", 10}]),
      board_threshold: 100
    }

    {:error, _} = Scenario.run(inputs)
    true = Scenario.rollouts() |> hd() |> Map.get(:status) == :rolled_back
    # node should be untouched (reservation never happened for c1)
    [node] = Scenario.nodes()
    true = node.slots_used == 0
    true = node.state == :idle
    IO.puts("INSUFFICIENT CAPACITY OK")
  end
end

defmodule PlanRolloutValidation do
  defp err?(targets) do
    case Orchestra.Fleet.plan_rollout(targets) do
      {:error, %Ash.Error.Invalid{errors: [%Ash.Error.Action.InvalidArgument{field: :targets} | _]}} ->
        true

      _ ->
        false
    end
  end

  def run do
    true = err?([])
    true = err?([%{node_name: "a", slots: 0}])
    true = err?([%{node_name: "a", slots: -1}])
    true = err?([%{node_name: "a", slots: "x"}])
    true = err?([%{node_name: "a", slots: 1}, %{node_name: "a", slots: 2}])

    {:ok, plan} = Orchestra.Fleet.plan_rollout([%{node_name: "b", slots: 2}, %{node_name: "a", slots: 3}])
    true = plan.total_slots == 5
    true = plan.node_names == ["a", "b"]
    true = plan.target_count == 2

    IO.puts("PLAN ROLLOUT VALIDATION OK")
  end
end

defmodule ApprovalLevels do
  def run do
    # auto
    Scenario.reset!()
    Scenario.flush!()
    Scenario.register!("a1", :us_east, 100)
    {:ok, _} = Scenario.run(%{rollout_name: "al1", strategy: :canary, targets: Scenario.targets([{"a1", 5}]), board_threshold: 10})
    true = Scenario.approvals() |> hd() |> Map.get(:level) == :auto

    # board (exactly at threshold)
    Scenario.reset!()
    Scenario.flush!()
    Scenario.register!("a2", :us_east, 100)
    {:ok, _} = Scenario.run(%{rollout_name: "al2", strategy: :canary, targets: Scenario.targets([{"a2", 10}]), board_threshold: 10})
    true = Scenario.approvals() |> hd() |> Map.get(:level) == :board

    IO.puts("APPROVAL LEVELS OK")
  end
end

defmodule DirectApprovalReactor do
  def run do
    Scenario.reset!()
    Scenario.flush!()
    {:ok, approval} =
      Reactor.run(Orchestra.Rollout.ApprovalReactor, %{rollout_id: "deadbeef-0000-0000-0000-000000000000", total_slots: 50, board_threshold: 10})

    true = is_struct(approval, Orchestra.Fleet.Approval)
    true = approval.level == :board
    true = approval.slots == 50
    true = approval.status == :granted
    true = approval.rollout_id == "deadbeef-0000-0000-0000-000000000000"

    {:ok, approval2} =
      Reactor.run(Orchestra.Rollout.ApprovalReactor, %{rollout_id: "feedface-0000-0000-0000-000000000000", total_slots: 5, board_threshold: 10})

    true = approval2.level == :auto

    IO.puts("DIRECT APPROVAL REACTOR OK")
  end
end

defmodule Introspection do
  defp step_types(steps) do
    steps
    |> Enum.flat_map(fn step ->
      type =
        cond do
          is_tuple(step.impl) and elem(step.impl, 0) == Ash.Reactor.CreateStep -> :create
          is_tuple(step.impl) and elem(step.impl, 0) == Ash.Reactor.UpdateStep -> :update
          is_tuple(step.impl) and elem(step.impl, 0) == Ash.Reactor.ReadOneStep -> :read
          is_tuple(step.impl) and elem(step.impl, 0) == Ash.Reactor.ActionStep -> :action
          is_tuple(step.impl) and elem(step.impl, 0) == Reactor.Step.Compose -> :compose
          is_tuple(step.impl) and elem(step.impl, 0) == Reactor.Step.Map -> :map
          is_tuple(step.impl) and elem(step.impl, 0) == Reactor.Step.Switch -> :switch
          is_tuple(step.impl) and elem(step.impl, 0) == Reactor.Step -> :step
          true -> :other
        end

      [type]
    end)
  end

  def run do
    {:ok, reactor} = Reactor.Info.to_struct(Orchestra.Rollout.Reactor)
    types = step_types(reactor.steps)
    true = :create in types
    true = :update in types
    true = :read in types
    true = :action in types
    true = :map in types
    true = :compose in types

    {:ok, approval_reactor} = Reactor.Info.to_struct(Orchestra.Rollout.ApprovalReactor)
    approval_types = step_types(approval_reactor.steps)
    true = :switch in approval_types
    true = :create in approval_types

    IO.puts("INTROSPECTION OK")
  end
end

defmodule Parallelism do
  def run do
    Scenario.reset!()
    Scenario.flush!()
    for i <- 1..6, do: Scenario.register!("p#{i}", :us_east, 10)

    inputs = %{
      rollout_name: "rollout-3",
      strategy: :canary,
      targets: Scenario.targets(for i <- 1..6, do: {"p#{i}", 1}),
      board_threshold: 100
    }

    {:ok, _} = Scenario.run(inputs)

    trace = Orchestra.Rollout.Trace.entries()

    {max_overlap, _} =
      Enum.reduce(trace, {0, 0}, fn
        {:deploy_enter, _}, {max, cur} -> {max(max, cur + 1), cur + 1}
        {:deploy_exit, _}, {max, cur} -> {max, cur - 1}
        _, acc -> acc
      end)

    true = max_overlap == 2
    IO.puts("PARALLELISM OK (max overlap #{max_overlap})")
  end
end

{:ok, _} = Application.ensure_all_started(:orchestra)

HappyPath.run()
FailurePath.run()
RetrySucceeds.run()
NodeNotFound.run()
InsufficientCapacity.run()
PlanRolloutValidation.run()
ApprovalLevels.run()
DirectApprovalReactor.run()
Introspection.run()
Parallelism.run()

IO.puts("ALL SCENARIOS PASSED")
