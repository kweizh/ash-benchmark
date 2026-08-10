import base64
import os
import subprocess

import pytest

PROJECT_DIR = "/home/user/sla_lab"
SUITE_PATH = "/tmp/harbor_expr_suite.exs"
RESULT_MARKER = "@@HARBOR@@"
SUITE_TIMEOUT = 1800

# A self-contained ExUnit suite. It is written to SUITE_PATH and executed with
# `mix run` from the project root so that it never depends on the layout of the
# project's own `test/` directory. Every module the executor has to provide is
# referenced through `Module.concat/1`, so the suite still compiles against an
# unsolved project and reports one failure per scenario instead of a single
# compile error.
SUITE_SOURCE = r"""
defmodule HarborFormatter do
  @moduledoc false
  use GenServer

  def init(opts), do: {:ok, opts}

  def handle_cast({:test_finished, %ExUnit.Test{} = test}, state) do
    {status, detail} =
      case test.state do
        nil ->
          {"pass", ""}

        {:failed, failures} ->
          {"fail",
           ExUnit.Formatter.format_test_failure(test, failures, 1, 120, fn _kind, msg -> msg end)}

        {:invalid, _} ->
          {"fail", "invalid test (setup failed)"}

        {:skipped, _} ->
          {"skip", ""}

        {:excluded, _} ->
          {"skip", ""}
      end

    IO.puts(
      "@@HARBOR@@" <>
        to_string(test.name) <> "@@" <> status <> "@@" <> Base.encode64(detail)
    )

    {:noreply, state}
  end

  def handle_cast(_event, state), do: {:noreply, state}
end

ExUnit.start(
  autorun: false,
  formatters: [HarborFormatter],
  seed: 0,
  colors: [enabled: false],
  timeout: 120_000
)

defmodule SlaLabSuite do
  use ExUnit.Case, async: false

  require Ash.Query
  import Ash.Expr

  @shipment SlaLab.Ops.Shipment
  @carrier SlaLab.Ops.Carrier
  @domain SlaLab.Ops
  @seed Module.concat(["SlaLab", "Ops", "Seed"])
  @route_key Module.concat(["SlaLab", "Expressions", "RouteKey"])
  @ratio Module.concat(["SlaLab", "Expressions", "RatioBps"])
  @penalty Module.concat(["SlaLab", "Expressions", "PenaltyPoints"])
  @validation Module.concat(["SlaLab", "Ops", "Validations", "RatioWithin"])

  setup do
    {:ok, apply(@seed, :seed!, [])}
  end

  defp refs(records), do: records |> Enum.map(& &1.reference) |> Enum.sort()

  defp read!(query), do: Ash.read!(query, authorize?: false)

  defp ev(expr), do: Ash.Expr.eval(expr)

  # ------------------------------------------------------------------
  # registration + module contracts
  # ------------------------------------------------------------------

  test "T01 custom expressions are registered with ash" do
    assert Ash.Filter.custom_expression(:route_key, ["ams", "jfk"]) ==
             {@route_key, ["ams", "jfk"]}

    assert Ash.Filter.custom_expression(:ratio_bps, [7, 2]) == {@ratio, [7, 2]}
    assert Ash.Filter.custom_expression(:ratio_bps, ["nope", "nah"]) == nil
  end

  test "T02 custom expression modules report name/0 and arguments/0" do
    assert @route_key.name() == :route_key
    assert @route_key.arguments() == [[:string, :string]]
    assert @ratio.name() == :ratio_bps
    assert @ratio.arguments() == [[:integer, :integer]]
  end

  test "T03 expression/2 dispatches per data layer" do
    assert {:ok, _} = Ash.CustomExpression.expression(@route_key, Ash.DataLayer.Ets, ["a", "b"])

    assert {:ok, _} =
             Ash.CustomExpression.expression(@route_key, Ash.DataLayer.Simple, ["a", "b"])

    assert :unknown =
             Ash.CustomExpression.expression(@route_key, Ash.DataLayer.Mnesia, ["a", "b"])

    assert {:ok, _} = Ash.CustomExpression.expression(@ratio, Ash.DataLayer.Ets, [1, 2])
    assert {:ok, _} = Ash.CustomExpression.expression(@ratio, Ash.DataLayer.Simple, [1, 2])
    assert :unknown = Ash.CustomExpression.expression(@ratio, Ash.DataLayer.Mnesia, [1, 2])
  end

  test "T04 both data layer clauses produce the same values" do
    for data_layer <- [Ash.DataLayer.Ets, Ash.DataLayer.Simple] do
      {:ok, expression} =
        Ash.CustomExpression.expression(@route_key, data_layer, ["jfk", "ams"])

      assert Ash.Expr.eval!(expression) == "AMS|JFK"

      {:ok, expression} = Ash.CustomExpression.expression(@ratio, data_layer, [1, 32])
      assert Ash.Expr.eval!(expression) == 313
    end
  end

  # ------------------------------------------------------------------
  # pure evaluation semantics
  # ------------------------------------------------------------------

  test "T05 route_key normalises and orders its arguments" do
    assert ev(expr(route_key("ams", "jfk"))) == {:ok, "AMS|JFK"}
    assert ev(expr(route_key("jfk", "ams"))) == {:ok, "AMS|JFK"}
    assert ev(expr(route_key("AMS", "ams"))) == {:ok, "AMS|AMS"}
    assert ev(expr(route_key("cdg", "ams"))) == {:ok, "AMS|CDG"}
    assert ev(expr(route_key(nil, "ams"))) == {:ok, nil}
    assert ev(expr(route_key("ams", nil))) == {:ok, nil}
  end

  test "T06 ratio_bps computes integral basis points" do
    assert ev(expr(ratio_bps(1, 3))) == {:ok, 3333}
    assert ev(expr(ratio_bps(2, 3))) == {:ok, 6667}
    assert ev(expr(ratio_bps(1, 2))) == {:ok, 5000}
    assert ev(expr(ratio_bps(3, 4))) == {:ok, 7500}
    assert ev(expr(ratio_bps(96, 48))) == {:ok, 20_000}

    {:ok, value} = ev(expr(ratio_bps(1, 3)))
    assert is_integer(value)
  end

  test "T07 ratio_bps rounds halves upwards" do
    assert ev(expr(ratio_bps(1, 32))) == {:ok, 313}
    assert ev(expr(ratio_bps(3, 32))) == {:ok, 938}
    assert ev(expr(ratio_bps(7, 32))) == {:ok, 2188}
    assert ev(expr(ratio_bps(1, 16))) == {:ok, 625}
    assert ev(expr(ratio_bps(1, 3200))) == {:ok, 3}
  end

  test "T08 ratio_bps clamps to the closed range 0..20000" do
    assert ev(expr(ratio_bps(3, 1))) == {:ok, 20_000}
    assert ev(expr(ratio_bps(5, 2))) == {:ok, 20_000}
    assert ev(expr(ratio_bps(0, 4))) == {:ok, 0}
    assert ev(expr(ratio_bps(-1, 4))) == {:ok, 0}
    assert ev(expr(ratio_bps(-9, 2))) == {:ok, 0}
  end

  test "T09 ratio_bps returns nil for nil arguments and a zero denominator" do
    assert ev(expr(ratio_bps(1, 0))) == {:ok, nil}
    assert ev(expr(ratio_bps(0, 0))) == {:ok, nil}
    assert ev(expr(ratio_bps(nil, 4))) == {:ok, nil}
    assert ev(expr(ratio_bps(4, nil))) == {:ok, nil}
  end

  test "T10 custom expressions compose with each other" do
    assert ev(expr(route_key(route_key("b", "a"), "zzz"))) == {:ok, "A|B|ZZZ"}
    assert ev(expr(ratio_bps(ratio_bps(1, 2), 10_000))) == {:ok, 5000}
    assert ev(expr(ratio_bps(1, 3) + ratio_bps(2, 3))) == {:ok, 10_000}
  end

  test "T11 custom expressions short circuit inside if/cond" do
    assert ev(expr(if(is_nil(nil), do: "pending", else: ratio_bps(1, 0)))) == {:ok, "pending"}

    assert ev(
             expr(
               cond do
                 ratio_bps(3, 4) > 8000 -> "high"
                 ratio_bps(3, 4) > 5000 -> "mid"
                 true -> "low"
               end
             )
           ) == {:ok, "mid"}

    assert ev(expr(if(ratio_bps(1, 0) > 1, do: "yes", else: "no"))) == {:ok, "no"}
  end

  test "T12 custom expression results can be cast with type/2" do
    assert ev(expr(type(ratio_bps(2, 3), :string))) == {:ok, "6667"}
    assert {:ok, %Decimal{} = decimal} = ev(expr(type(ratio_bps(2, 3), :decimal)))
    assert Decimal.equal?(decimal, Decimal.new(6667))
    assert ev(expr(string_join([route_key("b", "a"), "/", "x"]))) == {:ok, "A|B/x"}
  end

  test "T13 arguments outside the declared types are rejected" do
    assert Ash.Expr.eval(expr(ratio_bps(1, 2))) == {:ok, 5000}

    assert {:error, %Ash.Error.Query.NoSuchFunction{function: :ratio_bps}} =
             Ash.Expr.eval(expr(ratio_bps("abc", "def")))

    assert {:error, %Ash.Error.Invalid{errors: [%Ash.Error.Query.NoSuchFunction{} = error]}} =
             @shipment
             |> Ash.Query.filter(ratio_bps("abc", "def") > 1)
             |> Ash.read(authorize?: false)

    assert error.function == :ratio_bps
  end

  # ------------------------------------------------------------------
  # resource surfaces
  # ------------------------------------------------------------------

  test "T14 route_key is available as an expression calculation" do
    values =
      @shipment
      |> Ash.Query.load([:route_key])
      |> read!()
      |> Map.new(&{&1.reference, &1.route_key})

    assert values == %{
             "S01" => "AMS|JFK",
             "S02" => "AMS|JFK",
             "S03" => "AMS|LHR",
             "S04" => "AMS|LHR",
             "S05" => "HKG|SIN",
             "S06" => "HKG|SIN",
             "S07" => "NRT|SIN",
             "S08" => "AMS|OSL",
             "S09" => "AMS|OSL",
             "S10" => "AMS|CDG"
           }
  end

  test "T15 sla_ratio_bps is available as an expression calculation" do
    values =
      @shipment
      |> Ash.Query.load([:sla_ratio_bps])
      |> read!()
      |> Map.new(&{&1.reference, &1.sla_ratio_bps})

    assert values == %{
             "S01" => 5000,
             "S02" => 20_000,
             "S03" => nil,
             "S04" => 313,
             "S05" => 15_000,
             "S06" => 10_000,
             "S07" => 938,
             "S08" => nil,
             "S09" => nil,
             "S10" => 20_000
           }

    assert is_integer(values["S04"])
  end

  test "T16 status_label composes the custom expression with conditionals" do
    values =
      @shipment
      |> Ash.Query.load([:status_label])
      |> read!()
      |> Map.new(&{&1.reference, &1.status_label})

    assert values == %{
             "S01" => "met",
             "S02" => "breached",
             "S03" => "pending",
             "S04" => "met",
             "S05" => "breached",
             "S06" => "met",
             "S07" => "met",
             "S08" => "pending",
             "S09" => "pending",
             "S10" => "breached"
           }
  end

  test "T17 the on_route read action filters on the custom expression" do
    assert refs(apply(@domain, :shipments_on_route!, ["AMS|LHR", %{}, [authorize?: false]])) ==
             ["S03", "S04"]

    assert refs(apply(@domain, :shipments_on_route!, ["HKG|SIN", %{}, [authorize?: false]])) ==
             ["S05", "S06"]

    assert refs(apply(@domain, :shipments_on_route!, ["LHR|AMS", %{}, [authorize?: false]])) == []
  end

  test "T18 custom expressions can be used directly in a query filter" do
    records =
      @shipment
      |> Ash.Query.filter(ratio_bps(actual_hours, promised_hours) > 10_000)
      |> read!()

    assert refs(records) == ["S02", "S05", "S10"]

    records =
      @shipment
      |> Ash.Query.filter(route_key(origin_zone, destination_zone) == "AMS|OSL")
      |> read!()

    assert refs(records) == ["S08", "S09"]
  end

  test "T19 calculations built on custom expressions are filterable" do
    records =
      @shipment
      |> Ash.Query.filter(sla_ratio_bps <= 1000)
      |> read!()

    assert refs(records) == ["S04", "S07"]

    records =
      @shipment
      |> Ash.Query.filter(status_label == "pending")
      |> read!()

    assert refs(records) == ["S03", "S08", "S09"]
  end

  test "T20 calculations built on custom expressions are sortable" do
    ordered =
      @shipment
      |> Ash.Query.filter(not is_nil(actual_hours))
      |> Ash.Query.sort([{:sla_ratio_bps, :desc}, {:reference, :asc}])
      |> read!()
      |> Enum.map(& &1.reference)

    assert ordered == ["S02", "S10", "S05", "S06", "S01", "S07", "S04"]
  end

  test "T21 custom expressions can be sorted on inline" do
    ordered =
      @shipment
      |> Ash.Query.sort([
        {calc(route_key(origin_zone, destination_zone), type: :string), :asc},
        {:reference, :asc}
      ])
      |> read!()
      |> Enum.map(& &1.reference)

    assert ordered == ["S10", "S01", "S02", "S03", "S04", "S08", "S09", "S05", "S06", "S07"]
  end

  test "T22 aggregate filters accept custom expressions" do
    values =
      @carrier
      |> Ash.Query.load([:delivered_count, :breach_count])
      |> read!()
      |> Map.new(&{&1.code, {&1.delivered_count, &1.breach_count}})

    assert values == %{
             "NORDIC" => {4, 2},
             "PACIFIC" => {3, 1},
             "ARCTIC" => {0, 0}
           }
  end

  test "T23 custom expressions can be applied to aggregates" do
    values =
      @carrier
      |> Ash.Query.load([:breach_rate_bps])
      |> read!()
      |> Map.new(&{&1.code, &1.breach_rate_bps})

    assert values == %{"NORDIC" => 5000, "PACIFIC" => 3333, "ARCTIC" => nil}
  end

  test "T24 custom expressions over aggregates are filterable" do
    records =
      @carrier
      |> Ash.Query.filter(ratio_bps(breach_count, delivered_count) > 3333)
      |> read!()

    assert Enum.map(records, & &1.code) == ["NORDIC"]

    records =
      @carrier
      |> Ash.Query.filter(ratio_bps(breach_count, delivered_count) >= 3333)
      |> read!()

    assert records |> Enum.map(& &1.code) |> Enum.sort() == ["NORDIC", "PACIFIC"]
  end

  test "T25 custom expressions work inside exists/1" do
    records =
      @carrier
      |> Ash.Query.filter(exists(shipments, ratio_bps(actual_hours, promised_hours) > 10_000))
      |> read!()

    assert records |> Enum.map(& &1.code) |> Enum.sort() == ["NORDIC", "PACIFIC"]
  end

  # ------------------------------------------------------------------
  # validation
  # ------------------------------------------------------------------

  test "T26 record_delivery accepts a delivery within the allowed ratio", %{shipments: shipments} do
    action = Ash.Resource.Info.action(@shipment, :record_delivery)
    assert action.require_atomic? == true

    assert Enum.any?(action.changes, fn
             %Ash.Resource.Validation{module: module} -> module == @validation
             _other -> false
           end)

    {:ok, updated} =
      Ash.update(shipments["S03"], %{actual_hours: 36},
        action: :record_delivery,
        authorize?: false
      )

    assert updated.actual_hours == 36
  end

  test "T27 record_delivery rejects a delivery beyond the allowed ratio", %{
    shipments: shipments
  } do
    assert {:error, %Ash.Error.Invalid{errors: [error]}} =
             Ash.update(shipments["S03"], %{actual_hours: 37},
               action: :record_delivery,
               authorize?: false
             )

    assert %Ash.Error.Changes.InvalidAttribute{} = error
    assert error.field == :actual_hours
    assert error.message == "delivery ratio exceeds the allowed maximum"

    reloaded = Ash.get!(@shipment, shipments["S03"].id, authorize?: false)
    assert reloaded.actual_hours == nil
  end

  test "T28 the delivery validation is enforced atomically", %{shipments: _shipments} do
    result =
      @shipment
      |> Ash.Query.filter(reference == "S03")
      |> Ash.bulk_update(:record_delivery, %{actual_hours: 37},
        strategy: [:atomic],
        return_errors?: true,
        authorize?: false
      )

    assert result.status == :error
    assert result.error_count == 1

    result =
      @shipment
      |> Ash.Query.filter(reference == "S03")
      |> Ash.bulk_update(:record_delivery, %{actual_hours: 30},
        strategy: [:atomic],
        return_errors?: true,
        authorize?: false
      )

    assert result.status == :success
  end

  # ------------------------------------------------------------------
  # policies
  # ------------------------------------------------------------------

  test "T29 the read policy authorises on the custom expression" do
    records = Ash.read!(@shipment, actor: %{home_route: "AMS|LHR", role: :ops})
    assert refs(records) == ["S03", "S04"]

    records = Ash.read!(@shipment, actor: %{home_route: "NRT|SIN", role: :ops})
    assert refs(records) == ["S07"]

    records = Ash.read!(@shipment, actor: %{home_route: "AMS|OSL", role: :ops})
    assert refs(records) == ["S08", "S09"]
  end

  test "T30 admins bypass the route policy and anonymous readers are forbidden" do
    records = Ash.read!(@shipment, actor: %{role: :admin})
    assert length(records) == 10

    assert {:error, %Ash.Error.Forbidden{}} = Ash.read(@shipment, actor: nil)
  end

  # ------------------------------------------------------------------
  # custom query function
  # ------------------------------------------------------------------

  test "T31 the penalty_points function module reports its contract" do
    assert @penalty.name() == :penalty_points
    assert @penalty.args() == [[:integer, :integer]]
    assert @penalty.returns() == [:integer]
    assert @penalty.predicate?() == false
    assert @penalty.evaluate_nil_inputs?() == false
  end

  test "T32 penalty_points evaluates eagerly for literal arguments" do
    assert Ash.Query.Function.new(@penalty, [-5, 3]) == {:ok, 0}
    assert Ash.Query.Function.new(@penalty, [0, 3]) == {:ok, 0}
    assert Ash.Query.Function.new(@penalty, [1, 3]) == {:ok, 3}
    assert Ash.Query.Function.new(@penalty, [24, 3]) == {:ok, 72}
    assert Ash.Query.Function.new(@penalty, [25, 3]) == {:ok, 78}
    assert Ash.Query.Function.new(@penalty, [48, 2]) == {:ok, 144}
  end

  test "T33 penalty_points is never evaluated with nil arguments" do
    assert Ash.Query.Function.new(@penalty, [nil, 3]) == {:ok, nil}
    assert Ash.Query.Function.new(@penalty, [10, nil]) == {:ok, nil}
  end

  test "T34 penalty_points reports unknown and invalid inputs" do
    assert {:error, message} = Ash.Query.Function.new(@penalty, [1, 2, 3])
    assert is_binary(message)
    assert message =~ "penalty_points"

    assert @penalty.evaluate(struct(@penalty, arguments: ["10", 2])) == :unknown
    assert @penalty.evaluate(struct(@penalty, arguments: [10, 2])) == {:known, 20}

    assert @penalty.evaluate(struct(@penalty, arguments: [10, -1])) ==
             {:error, "penalty weight must not be negative"}
  end

  test "T35 penalty_points can be used inside a query filter" do
    {:ok, function} =
      Ash.Query.Function.new(@penalty, [expr(actual_hours - promised_hours), 2])

    records =
      @shipment
      |> Ash.Query.filter(^function > 48)
      |> read!()

    assert refs(records) == ["S02", "S10"]

    records =
      @shipment
      |> Ash.Query.filter(^function == 0)
      |> read!()

    assert refs(records) == ["S01", "S04", "S06", "S07"]
  end

  test "T36 penalty_points evaluates against a record", %{shipments: shipments} do
    {:ok, function} =
      Ash.Query.Function.new(@penalty, [expr(actual_hours - promised_hours), 2])

    assert Ash.Expr.eval(function, record: shipments["S05"], resource: @shipment) == {:ok, 12}
    assert Ash.Expr.eval(function, record: shipments["S02"], resource: @shipment) == {:ok, 144}
    assert Ash.Expr.eval(function, record: shipments["S03"], resource: @shipment) == {:ok, nil}

    assert Ash.Expr.eval(expr(^function + ratio_bps(actual_hours, promised_hours)),
             record: shipments["S05"],
             resource: @shipment
           ) == {:ok, 15_012}
  end

  test "T37 programmatically parsed filters behave identically" do
    expected =
      @shipment
      |> Ash.Query.filter(ratio_bps(actual_hours, promised_hours) > 10_000)
      |> read!()
      |> refs()

    filter =
      Ash.Filter.parse!(@shipment, expr(ratio_bps(actual_hours, promised_hours) > 10_000))

    actual =
      @shipment
      |> Ash.Query.do_filter(filter)
      |> read!()
      |> refs()

    assert actual == expected
    assert actual == ["S02", "S05", "S10"]
  end
end

ExUnit.run()
"""


def _run_suite():
    with open(SUITE_PATH, "w") as handle:
        handle.write(SUITE_SOURCE.lstrip("\n"))

    env = dict(os.environ)
    env["MIX_ENV"] = "dev"

    process = subprocess.run(
        ["mix", "run", SUITE_PATH],
        cwd=PROJECT_DIR,
        capture_output=True,
        text=True,
        timeout=SUITE_TIMEOUT,
        env=env,
    )

    results = {}
    for line in process.stdout.splitlines():
        if not line.startswith(RESULT_MARKER):
            continue
        parts = line.split("@@")
        if len(parts) < 5:
            continue
        name, status, encoded = parts[2], parts[3], parts[4]
        try:
            detail = base64.b64decode(encoded).decode("utf-8", "replace")
        except Exception:  # pragma: no cover - defensive
            detail = encoded
        results[name] = (status, detail)

    output_tail = (process.stdout[-6000:] + "\n" + process.stderr[-6000:]).strip()
    return {"results": results, "output": output_tail, "returncode": process.returncode}


@pytest.fixture(scope="session")
def suite():
    return _run_suite()


def check(suite, scenario):
    results = suite["results"]
    if not results:
        pytest.fail(
            "The ExUnit verification suite produced no results (the project most "
            "likely does not compile).\n"
            f"mix run exit code: {suite['returncode']}\n"
            f"output:\n{suite['output']}"
        )

    prefix = "test " + scenario + " "
    matching = [name for name in results if name.startswith(prefix)]
    assert matching, (
        f"Scenario {scenario} did not run. Known scenarios: {sorted(results)}\n"
        f"output:\n{suite['output']}"
    )

    name = matching[0]
    status, detail = results[name]
    assert status == "pass", f"Scenario {name} failed:\n{detail}"


def test_t01_custom_expressions_are_registered_with_ash(suite):
    """T01 custom expressions are registered with ash"""
    check(suite, "T01")


def test_t02_custom_expression_modules_report_name_0_and_arguments_0(suite):
    """T02 custom expression modules report name/0 and arguments/0"""
    check(suite, "T02")


def test_t03_expression_2_dispatches_per_data_layer(suite):
    """T03 expression/2 dispatches per data layer"""
    check(suite, "T03")


def test_t04_both_data_layer_clauses_produce_the_same_values(suite):
    """T04 both data layer clauses produce the same values"""
    check(suite, "T04")


def test_t05_route_key_normalises_and_orders_its_arguments(suite):
    """T05 route_key normalises and orders its arguments"""
    check(suite, "T05")


def test_t06_ratio_bps_computes_integral_basis_points(suite):
    """T06 ratio_bps computes integral basis points"""
    check(suite, "T06")


def test_t07_ratio_bps_rounds_halves_upwards(suite):
    """T07 ratio_bps rounds halves upwards"""
    check(suite, "T07")


def test_t08_ratio_bps_clamps_to_the_closed_range_0_20000(suite):
    """T08 ratio_bps clamps to the closed range 0..20000"""
    check(suite, "T08")


def test_t09_ratio_bps_returns_nil_for_nil_arguments_and_a_zero_denominator(suite):
    """T09 ratio_bps returns nil for nil arguments and a zero denominator"""
    check(suite, "T09")


def test_t10_custom_expressions_compose_with_each_other(suite):
    """T10 custom expressions compose with each other"""
    check(suite, "T10")


def test_t11_custom_expressions_short_circuit_inside_if_cond(suite):
    """T11 custom expressions short circuit inside if/cond"""
    check(suite, "T11")


def test_t12_custom_expression_results_can_be_cast_with_type_2(suite):
    """T12 custom expression results can be cast with type/2"""
    check(suite, "T12")


def test_t13_arguments_outside_the_declared_types_are_rejected(suite):
    """T13 arguments outside the declared types are rejected"""
    check(suite, "T13")


def test_t14_route_key_is_available_as_an_expression_calculation(suite):
    """T14 route_key is available as an expression calculation"""
    check(suite, "T14")


def test_t15_sla_ratio_bps_is_available_as_an_expression_calculation(suite):
    """T15 sla_ratio_bps is available as an expression calculation"""
    check(suite, "T15")


def test_t16_status_label_composes_the_custom_expression_with_conditionals(suite):
    """T16 status_label composes the custom expression with conditionals"""
    check(suite, "T16")


def test_t17_the_on_route_read_action_filters_on_the_custom_expression(suite):
    """T17 the on_route read action filters on the custom expression"""
    check(suite, "T17")


def test_t18_custom_expressions_can_be_used_directly_in_a_query_filter(suite):
    """T18 custom expressions can be used directly in a query filter"""
    check(suite, "T18")


def test_t19_calculations_built_on_custom_expressions_are_filterable(suite):
    """T19 calculations built on custom expressions are filterable"""
    check(suite, "T19")


def test_t20_calculations_built_on_custom_expressions_are_sortable(suite):
    """T20 calculations built on custom expressions are sortable"""
    check(suite, "T20")


def test_t21_custom_expressions_can_be_sorted_on_inline(suite):
    """T21 custom expressions can be sorted on inline"""
    check(suite, "T21")


def test_t22_aggregate_filters_accept_custom_expressions(suite):
    """T22 aggregate filters accept custom expressions"""
    check(suite, "T22")


def test_t23_custom_expressions_can_be_applied_to_aggregates(suite):
    """T23 custom expressions can be applied to aggregates"""
    check(suite, "T23")


def test_t24_custom_expressions_over_aggregates_are_filterable(suite):
    """T24 custom expressions over aggregates are filterable"""
    check(suite, "T24")


def test_t25_custom_expressions_work_inside_exists_1(suite):
    """T25 custom expressions work inside exists/1"""
    check(suite, "T25")


def test_t26_record_delivery_accepts_a_delivery_within_the_allowed_ratio(suite):
    """T26 record_delivery accepts a delivery within the allowed ratio"""
    check(suite, "T26")


def test_t27_record_delivery_rejects_a_delivery_beyond_the_allowed_ratio(suite):
    """T27 record_delivery rejects a delivery beyond the allowed ratio"""
    check(suite, "T27")


def test_t28_the_delivery_validation_is_enforced_atomically(suite):
    """T28 the delivery validation is enforced atomically"""
    check(suite, "T28")


def test_t29_the_read_policy_authorises_on_the_custom_expression(suite):
    """T29 the read policy authorises on the custom expression"""
    check(suite, "T29")


def test_t30_admins_bypass_the_route_policy_and_anonymous_readers_are_forbidden(suite):
    """T30 admins bypass the route policy and anonymous readers are forbidden"""
    check(suite, "T30")


def test_t31_the_penalty_points_function_module_reports_its_contract(suite):
    """T31 the penalty_points function module reports its contract"""
    check(suite, "T31")


def test_t32_penalty_points_evaluates_eagerly_for_literal_arguments(suite):
    """T32 penalty_points evaluates eagerly for literal arguments"""
    check(suite, "T32")


def test_t33_penalty_points_is_never_evaluated_with_nil_arguments(suite):
    """T33 penalty_points is never evaluated with nil arguments"""
    check(suite, "T33")


def test_t34_penalty_points_reports_unknown_and_invalid_inputs(suite):
    """T34 penalty_points reports unknown and invalid inputs"""
    check(suite, "T34")


def test_t35_penalty_points_can_be_used_inside_a_query_filter(suite):
    """T35 penalty_points can be used inside a query filter"""
    check(suite, "T35")


def test_t36_penalty_points_evaluates_against_a_record(suite):
    """T36 penalty_points evaluates against a record"""
    check(suite, "T36")


def test_t37_programmatically_parsed_filters_behave_identically(suite):
    """T37 programmatically parsed filters behave identically"""
    check(suite, "T37")
