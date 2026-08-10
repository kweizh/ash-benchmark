import base64
import os
import re
import shutil
import subprocess
import tempfile

import pytest

PROJECT_DIR = "/home/user/orchestra"
RESULT_PREFIX = "@@HARBOR@@"

# The suite below is a self-contained ExUnit script executed with `mix run` inside the
# solution project. It prints one machine readable line per finished test so that every
# behaviour is reported as its own pytest case.
SUITE_EXS = r"""
defmodule HarborFormatter do
  @moduledoc false
  use GenServer

  @impl true
  def init(opts), do: {:ok, opts}

  @impl true
  def handle_cast({:test_finished, %ExUnit.Test{} = test}, state) do
    {status, detail} =
      case test.state do
        nil ->
          {"pass", ""}

        {:skipped, _} ->
          {"skip", ""}

        {:excluded, _} ->
          {"skip", ""}

        {:failed, failures} ->
          {"fail",
           ExUnit.Formatter.format_test_failure(test, failures, 1, 200, fn _kind, msg -> msg end)}

        other ->
          {"fail", inspect(other)}
      end

    IO.puts(
      "@@HARBOR@@" <>
        to_string(test.name) <> "@@" <> status <> "@@" <> Base.encode64(to_string(detail))
    )

    {:noreply, state}
  end

  def handle_cast(_msg, state), do: {:noreply, state}
end

ExUnit.start(
  autorun: false,
  formatters: [HarborFormatter],
  seed: 0,
  colors: [enabled: false],
  timeout: 300_000,
  max_failures: :infinity
)

defmodule HarborSuite do
  use ExUnit.Case, async: false

  @fleet Orchestra.Fleet
  @reactor Orchestra.Rollout.Reactor
  @approval_reactor Orchestra.Rollout.ApprovalReactor
  @trace Orchestra.Rollout.Trace
  @deploy_step Orchestra.Rollout.Steps.DeployNode

  setup_all do
    try do
      build_state()
    rescue
      error -> %{fatal: Exception.format(:error, error, __STACKTRACE__)}
    catch
      kind, value -> %{fatal: Exception.format(kind, value, __STACKTRACE__)}
    end
  end

  defp build_state do
    # `Ash.DataLayer.Ets` creates each resource's table lazily, and a burst of
    # concurrent writes against a never-touched resource can race that creation.
    # Touch every table once up front so the scenarios below are deterministic.
    @fleet.list_nodes!()
    @fleet.list_rollouts!()
    @fleet.list_placements!()
    @fleet.list_approvals!()
    @fleet.list_leases!()

    register = fn name, total, budget ->
      @fleet.register_node!(name, :us_east, total, %{deploy_failures_remaining: budget})
    end

    run = fn name, targets, threshold, strategy ->
      @trace.reset()

      result =
        Reactor.run(@reactor, %{
          rollout_name: name,
          strategy: strategy,
          targets: targets,
          board_threshold: threshold
        })

      {result, @trace.entries()}
    end

    # --- happy path ---
    for n <- ~w(h1 h2 h3), do: register.(n, 8, 0)

    {happy_result, happy_trace} =
      run.(
        "rel-h",
        [
          %{node_name: "h1", slots: 2},
          %{node_name: "h2", slots: 3},
          %{node_name: "h3", slots: 1}
        ],
        100,
        :blast
      )

    # --- board approval ---
    for n <- ~w(b1 b2), do: register.(n, 8, 0)

    {board_result, _board_trace} =
      run.(
        "rel-b",
        [%{node_name: "b1", slots: 4}, %{node_name: "b2", slots: 5}],
        5,
        :canary
      )

    # --- retry ---
    register.("r1", 8, 0)
    register.("r2", 8, 3)
    register.("r3", 8, 0)

    {retry_result, retry_trace} =
      run.(
        "rel-r",
        [
          %{node_name: "r1", slots: 2},
          %{node_name: "r2", slots: 3},
          %{node_name: "r3", slots: 1}
        ],
        100,
        :canary
      )

    # --- rollback ---
    for n <- ~w(c1 c2 c3 c4 c5), do: register.(n, 8, 0)
    register.("c6", 8, 4)

    {rollback_result, rollback_trace} =
      run.("rel-c", for(i <- 1..6, do: %{node_name: "c#{i}", slots: 2}), 5, :blast)

    # --- reservation failure (insufficient slots) ---
    register.("s1", 8, 0)
    register.("s2", 2, 0)

    {slots_result, slots_trace} =
      run.(
        "rel-s",
        [%{node_name: "s1", slots: 1}, %{node_name: "s2", slots: 5}],
        100,
        :blast
      )

    # --- unknown node ---
    register.("u1", 8, 0)

    {unknown_result, _unknown_trace} =
      run.(
        "rel-u",
        [%{node_name: "u1", slots: 1}, %{node_name: "does-not-exist", slots: 1}],
        100,
        :blast
      )

    # --- recovery after failure ---
    for n <- ~w(w1 w2), do: register.(n, 8, 0)

    {recovery_result, _recovery_trace} =
      run.(
        "rel-w",
        [%{node_name: "w1", slots: 1}, %{node_name: "w2", slots: 2}],
        100,
        :blast
      )

    # --- standalone approval reactor ---
    approval_rollout_id = Ash.UUID.generate()

    standalone_board =
      Reactor.run(@approval_reactor, %{
        rollout_id: approval_rollout_id,
        total_slots: 9,
        board_threshold: 5
      })

    standalone_auto =
      Reactor.run(@approval_reactor, %{
        rollout_id: approval_rollout_id,
        total_slots: 2,
        board_threshold: 5
      })

    %{
      fatal: nil,
      happy_result: happy_result,
      happy_trace: happy_trace,
      board_result: board_result,
      retry_result: retry_result,
      retry_trace: retry_trace,
      rollback_result: rollback_result,
      rollback_trace: rollback_trace,
      slots_result: slots_result,
      slots_trace: slots_trace,
      unknown_result: unknown_result,
      recovery_result: recovery_result,
      standalone_board: standalone_board,
      standalone_auto: standalone_auto
    }
  end

  # ---------------------------------------------------------------- helpers

  defp ok!(ctx), do: assert(ctx[:fatal] == nil, "suite setup failed:\n#{ctx[:fatal]}")

  defp nodes(prefix) do
    @fleet.list_nodes!()
    |> Enum.filter(&String.starts_with?(&1.name, prefix))
    |> Map.new(&{&1.name, &1})
  end

  defp placements(names) do
    @fleet.list_placements!()
    |> Enum.filter(&(&1.node_name in names))
    |> Map.new(&{&1.node_name, &1})
  end

  defp rollout(name) do
    @fleet.list_rollouts!() |> Enum.filter(&(&1.name == name))
  end

  defp leases(name) do
    @fleet.list_leases!() |> Enum.filter(&(&1.rollout_name == name))
  end

  defp approvals(rollout_id) do
    @fleet.list_approvals!() |> Enum.filter(&(&1.rollout_id == rollout_id))
  end

  defp tags(trace, event) do
    for {e, l} <- trace, e == event, do: l
  end

  defp max_overlap(trace, prefix) do
    trace
    |> Enum.filter(fn {e, l} ->
      e in [:deploy_enter, :deploy_exit] and String.starts_with?(l, prefix)
    end)
    |> Enum.reduce({0, 0}, fn
      {:deploy_enter, _}, {cur, best} -> {cur + 1, Kernel.max(best, cur + 1)}
      {:deploy_exit, _}, {cur, best} -> {cur - 1, best}
    end)
    |> elem(1)
  end

  defp all_steps(reactor_module) do
    {:ok, reactor} = Reactor.Info.to_struct(reactor_module)
    walk(reactor.steps)
  end

  defp walk(steps) do
    Enum.flat_map(steps, fn step -> [step | walk(Reactor.Step.nested_steps(step))] end)
  end

  defp impl_module(%{impl: {module, _opts}}), do: module
  defp impl_module(%{impl: module}), do: module

  defp invalid_argument_error?({:error, %Ash.Error.Invalid{errors: errors}}) do
    Enum.any?(errors, fn
      %Ash.Error.Action.InvalidArgument{field: :targets} -> true
      _ -> false
    end)
  end

  defp invalid_argument_error?(_), do: false

  # ---------------------------------------------------------------- structure

  test "T01 the fleet domain exposes the five rollout resources", ctx do
    ok!(ctx)
    resources = Ash.Domain.Info.resources(@fleet)

    for module <- [
          Orchestra.Fleet.Node,
          Orchestra.Fleet.Rollout,
          Orchestra.Fleet.Placement,
          Orchestra.Fleet.Approval,
          Orchestra.Fleet.Lease
        ] do
      assert module in resources, "#{inspect(module)} is not registered in #{inspect(@fleet)}"
    end
  end

  test "T02 resource attributes have the required types and defaults", ctx do
    ok!(ctx)

    expected = [
      {Orchestra.Fleet.Node, :name, Ash.Type.String, :none},
      {Orchestra.Fleet.Node, :region, Ash.Type.Atom, :none},
      {Orchestra.Fleet.Node, :slots_total, Ash.Type.Integer, :none},
      {Orchestra.Fleet.Node, :slots_used, Ash.Type.Integer, 0},
      {Orchestra.Fleet.Node, :state, Ash.Type.Atom, :idle},
      {Orchestra.Fleet.Node, :deploy_failures_remaining, Ash.Type.Integer, 0},
      {Orchestra.Fleet.Rollout, :name, Ash.Type.String, :none},
      {Orchestra.Fleet.Rollout, :strategy, Ash.Type.Atom, :none},
      {Orchestra.Fleet.Rollout, :status, Ash.Type.Atom, :pending},
      {Orchestra.Fleet.Rollout, :deployed_node_count, Ash.Type.Integer, 0},
      {Orchestra.Fleet.Placement, :rollout_id, Ash.Type.UUID, :none},
      {Orchestra.Fleet.Placement, :node_name, Ash.Type.String, :none},
      {Orchestra.Fleet.Placement, :slots, Ash.Type.Integer, :none},
      {Orchestra.Fleet.Placement, :status, Ash.Type.Atom, :reserved},
      {Orchestra.Fleet.Placement, :attempts, Ash.Type.Integer, 0},
      {Orchestra.Fleet.Placement, :compensations, Ash.Type.Integer, 0},
      {Orchestra.Fleet.Placement, :undos, Ash.Type.Integer, 0},
      {Orchestra.Fleet.Approval, :rollout_id, Ash.Type.UUID, :none},
      {Orchestra.Fleet.Approval, :level, Ash.Type.Atom, :none},
      {Orchestra.Fleet.Approval, :slots, Ash.Type.Integer, :none},
      {Orchestra.Fleet.Approval, :status, Ash.Type.Atom, :granted},
      {Orchestra.Fleet.Lease, :rollout_name, Ash.Type.String, :none},
      {Orchestra.Fleet.Lease, :status, Ash.Type.Atom, :held}
    ]

    for {resource, name, type, default} <- expected do
      attribute = Ash.Resource.Info.attribute(resource, name)
      assert attribute, "#{inspect(resource)} is missing the attribute #{inspect(name)}"

      assert attribute.type == type,
             "#{inspect(resource)}.#{name} should be #{inspect(type)}, got #{inspect(attribute.type)}"

      if default != :none do
        assert attribute.default == default,
               "#{inspect(resource)}.#{name} should default to #{inspect(default)}, got #{inspect(attribute.default)}"
      end
    end
  end

  test "T03 the rollout reactor declares the four documented inputs", ctx do
    ok!(ctx)
    {:ok, reactor} = Reactor.Info.to_struct(@reactor)
    names = reactor.inputs |> Enum.map(& &1.name) |> Enum.sort()

    assert names == [:board_threshold, :rollout_name, :strategy, :targets],
           "unexpected reactor inputs: #{inspect(names)}"
  end

  test "T04 the rollout reactor installs a bespoke middleware module", ctx do
    ok!(ctx)

    custom =
      @reactor
      |> Reactor.Info.reactor_middlewares()
      |> Enum.map(& &1.module)
      |> Enum.reject(fn module ->
        name = Atom.to_string(module)
        String.starts_with?(name, "Elixir.Ash.") or String.starts_with?(name, "Elixir.Reactor.")
      end)

    assert custom != [],
           "the reactor must install a Reactor.Middleware module of its own"
  end

  test "T05 resource work is performed through Ash.Reactor action steps", ctx do
    ok!(ctx)
    impls = @reactor |> all_steps() |> Enum.map(&impl_module/1) |> MapSet.new()

    for module <- [Ash.Reactor.CreateStep, Ash.Reactor.UpdateStep, Ash.Reactor.ActionStep] do
      assert module in impls,
             "expected the reactor to contain an #{inspect(module)} step, got #{inspect(MapSet.to_list(impls))}"
    end

    assert Ash.Reactor.ReadStep in impls or Ash.Reactor.ReadOneStep in impls,
           "expected the reactor to read a resource through an Ash.Reactor read step"
  end

  test "T06 the reactor maps over targets and composes the approval reactor", ctx do
    ok!(ctx)
    steps = all_steps(@reactor)
    impls = Enum.map(steps, &impl_module/1)

    assert Reactor.Step.Map in impls, "expected at least one map step in the reactor"

    assert Reactor.Step.Compose in impls,
           "expected the reactor to embed the approval reactor with a compose step"

    assert @deploy_step in impls,
           "#{inspect(@deploy_step)} must be used as a step implementation in the reactor"
  end

  test "T07 the deployment step implements the Reactor.Step callbacks", ctx do
    ok!(ctx)
    Code.ensure_loaded?(@deploy_step)

    for {fun, arity} <- [{:run, 3}, {:compensate, 4}, {:undo, 4}] do
      assert function_exported?(@deploy_step, fun, arity),
             "#{inspect(@deploy_step)} must export #{fun}/#{arity}"
    end
  end

  test "T08 the approval reactor branches with a switch step", ctx do
    ok!(ctx)
    impls = @approval_reactor |> all_steps() |> Enum.map(&impl_module/1)

    assert Reactor.Step.Switch in impls,
           "the approval reactor must pick the approval level with a switch step"
  end

  # ---------------------------------------------------------------- planning

  test "T09 the planning action summarises the targets", ctx do
    ok!(ctx)

    assert @fleet.plan_rollout!([
             %{node_name: "p2", slots: 3},
             %{node_name: "p1", slots: 4}
           ]) == %{total_slots: 7, node_names: ["p1", "p2"], target_count: 2}
  end

  test "T10 the planning action rejects an empty target list", ctx do
    ok!(ctx)
    result = @fleet.plan_rollout([])

    assert invalid_argument_error?(result),
           "expected an Ash.Error.Invalid carrying an InvalidArgument for :targets, got #{inspect(result)}"
  end

  test "T11 the planning action rejects duplicate node names", ctx do
    ok!(ctx)
    result = @fleet.plan_rollout([%{node_name: "p1", slots: 1}, %{node_name: "p1", slots: 2}])

    assert invalid_argument_error?(result),
           "expected an Ash.Error.Invalid carrying an InvalidArgument for :targets, got #{inspect(result)}"
  end

  test "T12 the planning action rejects non-positive slot counts", ctx do
    ok!(ctx)
    result = @fleet.plan_rollout([%{node_name: "p1", slots: 0}])

    assert invalid_argument_error?(result),
           "expected an Ash.Error.Invalid carrying an InvalidArgument for :targets, got #{inspect(result)}"
  end

  # ---------------------------------------------------------------- happy path

  test "T13 a clean rollout returns the documented result map", ctx do
    ok!(ctx)
    assert {:ok, result} = ctx.happy_result

    assert Enum.sort(Map.keys(result)) ==
             Enum.sort([
               :rollout_id,
               :status,
               :deployed_nodes,
               :total_slots,
               :approval_level,
               :summary
             ]),
           "unexpected result keys: #{inspect(Map.keys(result))}"

    assert result.status == :succeeded
    assert result.deployed_nodes == ["h1", "h2", "h3"]
    assert result.total_slots == 6
    assert result.approval_level == :auto
  end

  test "T14 the rollout summary is rendered exactly", ctx do
    ok!(ctx)
    assert {:ok, result} = ctx.happy_result

    assert result.summary ==
             "Rollout rel-h deployed 3 node(s) in blast mode with auto approval."
  end

  test "T15 a clean rollout leaves every target node live and reserved", ctx do
    ok!(ctx)
    nodes = nodes("h")

    for {name, slots} <- [{"h1", 2}, {"h2", 3}, {"h3", 1}] do
      node = nodes[name]
      assert node, "node #{name} disappeared"
      assert node.slots_used == slots, "#{name}.slots_used == #{inspect(node.slots_used)}"
      assert node.state == :live, "#{name}.state == #{inspect(node.state)}"
    end
  end

  test "T16 a clean rollout deploys every placement exactly once", ctx do
    ok!(ctx)
    assert {:ok, result} = ctx.happy_result
    placements = placements(["h1", "h2", "h3"])
    assert map_size(placements) == 3, "expected 3 placements, got #{map_size(placements)}"

    for {name, placement} <- placements do
      assert placement.status == :deployed, "#{name} status #{inspect(placement.status)}"
      assert placement.attempts == 1, "#{name} attempts #{placement.attempts}"
      assert placement.compensations == 0, "#{name} compensations #{placement.compensations}"
      assert placement.undos == 0, "#{name} undos #{placement.undos}"
      assert placement.rollout_id == result.rollout_id, "#{name} has the wrong rollout_id"
    end
  end

  test "T17 a clean rollout is marked succeeded", ctx do
    ok!(ctx)
    assert [record] = rollout("rel-h")
    assert record.status == :succeeded
    assert record.deployed_node_count == 3
    assert record.strategy == :blast
  end

  test "T18 a clean rollout releases its lease and keeps the approval granted", ctx do
    ok!(ctx)
    assert {:ok, result} = ctx.happy_result
    assert [lease] = leases("rel-h")
    assert lease.status == :released

    assert [approval] = approvals(result.rollout_id)
    assert approval.level == :auto
    assert approval.slots == 6
    assert approval.status == :granted
  end

  test "T19 the middleware records the reactor lifecycle of a clean run", ctx do
    ok!(ctx)
    trace = ctx.happy_trace

    assert Enum.count(trace, &(&1 == {:reactor_init, "reactor"})) == 1
    assert Enum.count(trace, &(&1 == {:reactor_complete, "reactor"})) == 1
    assert Enum.count(trace, fn {event, _} -> event == :reactor_error end) == 0
    assert Enum.any?(trace, fn {event, _} -> event == :run_start end)
    assert Enum.any?(trace, fn {event, _} -> event == :process_start end)
  end

  # ---------------------------------------------------------------- approval

  test "T20 a large rollout requires board approval", ctx do
    ok!(ctx)
    assert {:ok, result} = ctx.board_result
    assert result.approval_level == :board
    assert String.ends_with?(result.summary, "with board approval.")

    assert [approval] = approvals(result.rollout_id)
    assert approval.level == :board
    assert approval.slots == 9
    assert approval.status == :granted
  end

  test "T21 the approval reactor runs standalone and switches on the total", ctx do
    ok!(ctx)
    assert {:ok, board} = ctx.standalone_board
    assert board.__struct__ == Orchestra.Fleet.Approval
    assert board.level == :board
    assert board.slots == 9
    assert board.status == :granted

    assert {:ok, auto} = ctx.standalone_auto
    assert auto.level == :auto
  end

  # ---------------------------------------------------------------- retries

  test "T22 a transiently failing node is retried until it deploys", ctx do
    ok!(ctx)
    assert {:ok, _} = ctx.retry_result
    node = @fleet.get_node!("r2")
    assert node.deploy_failures_remaining == 0
    assert node.state == :live
  end

  test "T23 retry and compensation counters are recorded per placement", ctx do
    ok!(ctx)
    placements = placements(["r1", "r2", "r3"])

    assert placements["r2"].attempts == 4
    assert placements["r2"].compensations == 3
    assert placements["r2"].undos == 0
    assert placements["r2"].status == :deployed

    for name <- ["r1", "r3"] do
      assert placements[name].attempts == 1, "#{name} attempts #{placements[name].attempts}"

      assert placements[name].compensations == 0,
             "#{name} compensations #{placements[name].compensations}"
    end
  end

  test "T24 each failed attempt is compensated before the next one starts", ctx do
    ok!(ctx)

    sequence =
      for {event, label} <- ctx.retry_trace,
          label == "r2",
          event in [:deploy_enter, :deploy_exit, :deploy_compensate],
          do: event

    assert sequence == [
             :deploy_enter,
             :deploy_exit,
             :deploy_compensate,
             :deploy_enter,
             :deploy_exit,
             :deploy_compensate,
             :deploy_enter,
             :deploy_exit,
             :deploy_compensate,
             :deploy_enter,
             :deploy_exit
           ],
           "unexpected attempt/compensation sequence: #{inspect(sequence)}"
  end

  # ---------------------------------------------------------------- rollback

  test "T25 exhausting the retry budget fails the rollout", ctx do
    ok!(ctx)
    assert {:error, _} = ctx.rollback_result
  end

  test "T26 a failed rollout returns every node to its original capacity", ctx do
    ok!(ctx)
    nodes = nodes("c")

    for i <- 1..6 do
      name = "c#{i}"
      node = nodes[name]
      assert node, "node #{name} disappeared"
      assert node.slots_used == 0, "#{name}.slots_used == #{inspect(node.slots_used)}"
      assert node.state == :idle, "#{name}.state == #{inspect(node.state)}"
    end
  end

  test "T27 a failed rollout undoes only the placements that had deployed", ctx do
    ok!(ctx)
    names = for i <- 1..6, do: "c#{i}"
    placements = placements(names)
    assert map_size(placements) == 6, "expected 6 placements, got #{map_size(placements)}"

    for i <- 1..5 do
      name = "c#{i}"
      placement = placements[name]
      assert placement.status == :released, "#{name} status #{inspect(placement.status)}"
      assert placement.attempts == 1, "#{name} attempts #{placement.attempts}"
      assert placement.compensations == 0, "#{name} compensations #{placement.compensations}"
      assert placement.undos == 1, "#{name} undos #{placement.undos}"
    end

    failed = placements["c6"]
    assert failed.status == :reserved, "c6 status #{inspect(failed.status)}"
    assert failed.attempts == 4, "c6 attempts #{failed.attempts}"
    assert failed.compensations == 4, "c6 compensations #{failed.compensations}"
    assert failed.undos == 0, "c6 undos #{failed.undos}"
  end

  test "T28 a failed rollout rolls back the rollout, lease and approval", ctx do
    ok!(ctx)
    assert [record] = rollout("rel-c")
    assert record.status == :rolled_back
    assert record.deployed_node_count == 0

    assert [lease] = leases("rel-c")
    assert lease.status == :released

    assert [approval] = approvals(record.id)
    assert approval.level == :board
    assert approval.status == :revoked
  end

  test "T29 the trace records one undo per unit of completed work", ctx do
    ok!(ctx)
    trace = ctx.rollback_trace

    assert Enum.sort(tags(trace, :deploy_undo)) == ["c1", "c2", "c3", "c4", "c5"],
           "unexpected deploy undos: #{inspect(tags(trace, :deploy_undo))}"

    assert Enum.sort(tags(trace, :reserve_undo)) == ["c1", "c2", "c3", "c4", "c5", "c6"],
           "unexpected reservation undos: #{inspect(tags(trace, :reserve_undo))}"

    assert Enum.count(trace, &(&1 == {:deploy_compensate, "c6"})) == 4,
           "expected four compensations for c6"
  end

  test "T30 rollback only begins once the failing step is out of attempts", ctx do
    ok!(ctx)
    trace = ctx.rollback_trace
    indexed = Enum.with_index(trace)

    last_compensate =
      indexed
      |> Enum.filter(fn {{event, _}, _} -> event == :deploy_compensate end)
      |> Enum.map(&elem(&1, 1))
      |> Enum.max()

    first_undo =
      indexed
      |> Enum.filter(fn {{event, _}, _} -> event in [:deploy_undo, :reserve_undo] end)
      |> Enum.map(&elem(&1, 1))
      |> Enum.min()

    assert first_undo > last_compensate,
           "an undo was recorded at position #{first_undo}, before the last compensation at #{last_compensate}"

    assert Enum.count(trace, &(&1 == {:reactor_error, "reactor"})) == 1
    assert Enum.count(trace, fn {event, _} -> event == :reactor_complete end) == 0
    assert Enum.any?(trace, fn {event, _} -> event == :undo_start end)
  end

  test "T31 deployments run two at a time", ctx do
    ok!(ctx)

    assert max_overlap(ctx.rollback_trace, "c") == 2,
           "expected exactly two concurrent deployments, observed #{max_overlap(ctx.rollback_trace, "c")}"
  end

  # ---------------------------------------------------------------- early failure

  test "T32 an impossible reservation aborts before any deployment starts", ctx do
    ok!(ctx)
    assert {:error, _} = ctx.slots_result

    assert Enum.count(ctx.slots_trace, fn {event, _} -> event == :deploy_enter end) == 0,
           "no deployment may start when a reservation failed"

    nodes = nodes("s")

    for name <- ["s1", "s2"] do
      assert nodes[name].slots_used == 0, "#{name}.slots_used == #{nodes[name].slots_used}"
      assert nodes[name].state == :idle, "#{name}.state == #{inspect(nodes[name].state)}"
    end

    assert [record] = rollout("rel-s")
    assert record.status == :rolled_back
    assert [lease] = leases("rel-s")
    assert lease.status == :released

    assert Enum.all?(placements(["s1", "s2"]), fn {_, placement} ->
             placement.status != :deployed
           end),
           "no placement may be deployed when a reservation failed"
  end

  test "T33 an unknown target node aborts and releases everything", ctx do
    ok!(ctx)
    assert {:error, _} = ctx.unknown_result

    node = @fleet.get_node!("u1")
    assert node.slots_used == 0
    assert node.state == :idle

    assert [record] = rollout("rel-u")
    assert record.status == :rolled_back
    assert [lease] = leases("rel-u")
    assert lease.status == :released
  end

  # ---------------------------------------------------------------- recovery

  test "T34 a later rollout still succeeds after a failed one", ctx do
    ok!(ctx)
    assert {:ok, result} = ctx.recovery_result
    assert result.status == :succeeded
    assert result.deployed_nodes == ["w1", "w2"]

    assert [record] = rollout("rel-w")
    assert record.status == :succeeded
    assert [lease] = leases("rel-w")
    assert lease.status == :released
    assert [approval] = approvals(result.rollout_id)
    assert approval.status == :granted

    assert [previous] = rollout("rel-c")
    assert previous.status == :rolled_back
  end

  test "T35 the trace can be reset", ctx do
    ok!(ctx)
    assert @trace.reset() == :ok
    assert @trace.entries() == []
  end
end

ExUnit.run()
"""


def _parse(output):
    results = {}
    for line in output.splitlines():
        if not line.startswith(RESULT_PREFIX):
            continue
        body = line[len(RESULT_PREFIX):]
        parts = body.split("@@")
        if len(parts) < 3:
            continue
        name, status, encoded = parts[0], parts[1], parts[2]
        match = re.match(r"test (T\d+)\b", name)
        if not match:
            continue

        try:
            detail = base64.b64decode(encoded).decode("utf-8", "replace")
        except Exception:  # pragma: no cover - defensive
            detail = encoded
        results[match.group(1)] = (status, detail, name)
    return results


@pytest.fixture(scope="session")
def suite_results():
    assert os.path.isdir(PROJECT_DIR), f"{PROJECT_DIR} does not exist."
    assert shutil.which("mix") is not None, "`mix` was not found in PATH."

    workdir = tempfile.mkdtemp(prefix="harbor-reactor-", dir=os.path.expanduser("~"))
    script = os.path.join(workdir, "harbor_reactor_suite.exs")
    with open(script, "w") as handle:
        handle.write(SUITE_EXS.lstrip("\n"))

    env = os.environ.copy()
    env.setdefault("MIX_ENV", "dev")
    env.setdefault("LANG", "C.UTF-8")

    try:
        completed = subprocess.run(
            ["mix", "run", script],
            cwd=PROJECT_DIR,
            capture_output=True,
            text=True,
            timeout=900,
            env=env,
        )
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    output = (completed.stdout or "") + "\n" + (completed.stderr or "")
    results = _parse(output)
    tail = output[-6000:]
    return {"results": results, "output": tail, "returncode": completed.returncode}


def _check(suite, test_id):
    results = suite["results"]
    if test_id not in results:
        pytest.fail(
            f"scenario {test_id} produced no result. The ExUnit suite most likely failed to "
            f"compile or run against the solution.\n"
            f"`mix run` exited with {suite['returncode']}.\n"
            f"--- output tail ---\n{suite['output']}"
        )
    status, detail, name = results[test_id]
    assert status == "pass", f"{name} failed:\n{detail}"


def test_t01_the_fleet_domain_exposes_the_five_rollout_resources(suite_results):
    """T01 — the fleet domain exposes the five rollout resources."""
    _check(suite_results, "T01")


def test_t02_resource_attributes_have_the_required_types_and_defaults(suite_results):
    """T02 — resource attributes have the required types and defaults."""
    _check(suite_results, "T02")


def test_t03_the_rollout_reactor_declares_the_four_documented_inputs(suite_results):
    """T03 — the rollout reactor declares the four documented inputs."""
    _check(suite_results, "T03")


def test_t04_the_rollout_reactor_installs_a_bespoke_middleware_module(suite_results):
    """T04 — the rollout reactor installs a bespoke middleware module."""
    _check(suite_results, "T04")


def test_t05_resource_work_is_performed_through_ash_reactor_action_steps(suite_results):
    """T05 — resource work is performed through Ash.Reactor action steps."""
    _check(suite_results, "T05")


def test_t06_the_reactor_maps_over_targets_and_composes_the_approval_reactor(suite_results):
    """T06 — the reactor maps over targets and composes the approval reactor."""
    _check(suite_results, "T06")


def test_t07_the_deployment_step_implements_the_reactor_step_callbacks(suite_results):
    """T07 — the deployment step implements the Reactor.Step callbacks."""
    _check(suite_results, "T07")


def test_t08_the_approval_reactor_branches_with_a_switch_step(suite_results):
    """T08 — the approval reactor branches with a switch step."""
    _check(suite_results, "T08")


def test_t09_the_planning_action_summarises_the_targets(suite_results):
    """T09 — the planning action summarises the targets."""
    _check(suite_results, "T09")


def test_t10_the_planning_action_rejects_an_empty_target_list(suite_results):
    """T10 — the planning action rejects an empty target list."""
    _check(suite_results, "T10")


def test_t11_the_planning_action_rejects_duplicate_node_names(suite_results):
    """T11 — the planning action rejects duplicate node names."""
    _check(suite_results, "T11")


def test_t12_the_planning_action_rejects_non_positive_slot_counts(suite_results):
    """T12 — the planning action rejects non-positive slot counts."""
    _check(suite_results, "T12")


def test_t13_a_clean_rollout_returns_the_documented_result_map(suite_results):
    """T13 — a clean rollout returns the documented result map."""
    _check(suite_results, "T13")


def test_t14_the_rollout_summary_is_rendered_exactly(suite_results):
    """T14 — the rollout summary is rendered exactly."""
    _check(suite_results, "T14")


def test_t15_a_clean_rollout_leaves_every_target_node_live_and_reserved(suite_results):
    """T15 — a clean rollout leaves every target node live and reserved."""
    _check(suite_results, "T15")


def test_t16_a_clean_rollout_deploys_every_placement_exactly_once(suite_results):
    """T16 — a clean rollout deploys every placement exactly once."""
    _check(suite_results, "T16")


def test_t17_a_clean_rollout_is_marked_succeeded(suite_results):
    """T17 — a clean rollout is marked succeeded."""
    _check(suite_results, "T17")


def test_t18_a_clean_rollout_releases_its_lease_and_keeps_the_approval_granted(suite_results):
    """T18 — a clean rollout releases its lease and keeps the approval granted."""
    _check(suite_results, "T18")


def test_t19_the_middleware_records_the_reactor_lifecycle_of_a_clean_run(suite_results):
    """T19 — the middleware records the reactor lifecycle of a clean run."""
    _check(suite_results, "T19")


def test_t20_a_large_rollout_requires_board_approval(suite_results):
    """T20 — a large rollout requires board approval."""
    _check(suite_results, "T20")


def test_t21_the_approval_reactor_runs_standalone_and_switches_on_the_total(suite_results):
    """T21 — the approval reactor runs standalone and switches on the total."""
    _check(suite_results, "T21")


def test_t22_a_transiently_failing_node_is_retried_until_it_deploys(suite_results):
    """T22 — a transiently failing node is retried until it deploys."""
    _check(suite_results, "T22")


def test_t23_retry_and_compensation_counters_are_recorded_per_placement(suite_results):
    """T23 — retry and compensation counters are recorded per placement."""
    _check(suite_results, "T23")


def test_t24_each_failed_attempt_is_compensated_before_the_next_one_starts(suite_results):
    """T24 — each failed attempt is compensated before the next one starts."""
    _check(suite_results, "T24")


def test_t25_exhausting_the_retry_budget_fails_the_rollout(suite_results):
    """T25 — exhausting the retry budget fails the rollout."""
    _check(suite_results, "T25")


def test_t26_a_failed_rollout_returns_every_node_to_its_original_capacity(suite_results):
    """T26 — a failed rollout returns every node to its original capacity."""
    _check(suite_results, "T26")


def test_t27_a_failed_rollout_undoes_only_the_placements_that_had_deployed(suite_results):
    """T27 — a failed rollout undoes only the placements that had deployed."""
    _check(suite_results, "T27")


def test_t28_a_failed_rollout_rolls_back_the_rollout_lease_and_approval(suite_results):
    """T28 — a failed rollout rolls back the rollout, lease and approval."""
    _check(suite_results, "T28")


def test_t29_the_trace_records_one_undo_per_unit_of_completed_work(suite_results):
    """T29 — the trace records one undo per unit of completed work."""
    _check(suite_results, "T29")


def test_t30_rollback_only_begins_once_the_failing_step_is_out_of_attempts(suite_results):
    """T30 — rollback only begins once the failing step is out of attempts."""
    _check(suite_results, "T30")


def test_t31_deployments_run_two_at_a_time(suite_results):
    """T31 — deployments run two at a time."""
    _check(suite_results, "T31")


def test_t32_an_impossible_reservation_aborts_before_any_deployment_starts(suite_results):
    """T32 — an impossible reservation aborts before any deployment starts."""
    _check(suite_results, "T32")


def test_t33_an_unknown_target_node_aborts_and_releases_everything(suite_results):
    """T33 — an unknown target node aborts and releases everything."""
    _check(suite_results, "T33")


def test_t34_a_later_rollout_still_succeeds_after_a_failed_one(suite_results):
    """T34 — a later rollout still succeeds after a failed one."""
    _check(suite_results, "T34")


def test_t35_the_trace_can_be_reset(suite_results):
    """T35 — the trace can be reset."""
    _check(suite_results, "T35")
