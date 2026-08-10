"""Final-state verification for the ash_bulk_actions_stream_pipeline task.

The whole behavioural contract is exercised by a self-contained ExUnit script that is
written to /tmp at verification time and executed with `mix run` inside the project, so
nothing is added to the executor's project tree. Each ExUnit scenario prints one
`@@HARBOR@@<name>@@<status>@@<base64 detail>` line, and one pytest function below reports
each scenario individually.
"""

import base64
import os
import subprocess

import pytest

PROJECT_DIR = "/home/user/ingest"
SUITE_PATH = "/tmp/harbor_bulk_pipeline_suite.exs"
MARKER = "@@HARBOR@@"

SUITE_SOURCE = r"""
defmodule HarborFormatter do
  @moduledoc false
  use GenServer

  def init(_opts), do: {:ok, %{}}

  def handle_cast({:test_finished, %ExUnit.Test{} = test}, state) do
    {status, detail} =
      case test.state do
        nil ->
          {"passed", ""}

        {:excluded, _} ->
          {"skipped", ""}

        {:skipped, _} ->
          {"skipped", ""}

        {:invalid, _} ->
          {"failed", "invalid test (setup failed)"}

        {:failed, failures} ->
          {"failed",
           ExUnit.Formatter.format_test_failure(test, failures, 1, 120, fn _, msg -> msg end)}
      end

    IO.puts("@@HARBOR@@#{test.name}@@#{status}@@#{Base.encode64(detail)}")
    {:noreply, state}
  end

  def handle_cast(_, state), do: {:noreply, state}
end

ExUnit.start(
  autorun: false,
  formatters: [HarborFormatter],
  seed: 0,
  colors: [enabled: false],
  timeout: 120_000
)

defmodule H do
  @moduledoc false
  require Ash.Query

  alias Ingest.Pipeline.Meter
  alias Ingest.Pipeline.MeterRollup
  alias Ingest.Pipeline.Reading

  def domain, do: Ingest.Pipeline
  def reading, do: Reading
  def rollup, do: MeterRollup

  def reset! do
    Ingest.Pipeline.Store.reset!()
  end

  def seed_meters! do
    Ash.create!(Meter, %{code: "M-ALPHA", scale_bp: 10_000, active: true})
    Ash.create!(Meter, %{code: "M-BETA", scale_bp: 12_500, active: true})
    Ash.create!(Meter, %{code: "M-GAMMA", scale_bp: 9_500, active: true})
    Ash.create!(Meter, %{code: "M-OFF", scale_bp: 10_000, active: false})
    :ok
  end

  def setup! do
    reset!()
    seed_meters!()
    :ok
  end

  def row(eid, code, kwh, day \\ 1) do
    %{
      external_id: eid,
      meter_code: code,
      raw_kwh: kwh,
      recorded_on: Date.add(~D[2026-03-01], day)
    }
  end

  def ingest(rows, batch_ref, opts \\ []) do
    Ingest.Pipeline.Ingestion.ingest(rows, batch_ref, opts)
  end

  def readings do
    Reading |> Ash.read!() |> Enum.sort_by(& &1.external_id)
  end

  def by_eid(eid) do
    Reading |> Ash.Query.filter(external_id == ^eid) |> Ash.read_one!()
  end

  def rollups do
    MeterRollup |> Ash.read!() |> Enum.sort_by(& &1.meter_code)
  end

  def rollup_for(code) do
    MeterRollup |> Ash.Query.filter(meter_code == ^code) |> Ash.read_one!()
  end

  def seed_reading!(attrs) do
    defaults = %{
      net_kwh: nil,
      status: :pending,
      batch_ref: "SEED",
      recorded_on: ~D[2026-03-01]
    }

    Ash.Seed.seed!(Reading, Map.merge(defaults, attrs))
  end

  @doc "Runs fun/0 while counting data-layer reads of `resource`."
  def count_reads(resource, fun) do
    counter = :counters.new(1, [])
    handler_id = "harbor-reads-#{System.unique_integer([:positive])}"

    :telemetry.attach(
      handler_id,
      [:ash, :pipeline, :read, :stop],
      fn _event, _measure, meta, _config ->
        if Map.get(meta, :resource) == resource, do: :counters.add(counter, 1, 1)
      end,
      nil
    )

    try do
      result = fun.()
      {result, :counters.get(counter, 1)}
    after
      :telemetry.detach(handler_id)
    end
  end

  def error_fields(%{errors: errors}) do
    Enum.flat_map(errors, &error_fields/1)
  end

  def error_fields(error) do
    nested = Map.get(error, :errors)

    if is_list(nested) and nested != [] do
      Enum.flat_map(nested, &error_fields/1)
    else
      field = Map.get(error, :field)
      fields = Map.get(error, :fields) || []
      Enum.reject([field | fields], &is_nil/1)
    end
  end
end

defmodule HarborTest do
  use ExUnit.Case, async: false
  require Ash.Query

  alias Ingest.Pipeline.Meter
  alias Ingest.Pipeline.MeterRollup
  alias Ingest.Pipeline.Reading

  setup do
    H.setup!()
    :ok
  end

  # ----------------------------------------------------------------- structure

  test "T01 Reading and MeterRollup are ETS-backed resources of the domain" do
    resources = Ash.Domain.Info.resources(Ingest.Pipeline)
    assert Reading in resources
    assert MeterRollup in resources
    assert Ash.Resource.Info.data_layer(Reading) == Ash.DataLayer.Ets
    assert Ash.Resource.Info.data_layer(MeterRollup) == Ash.DataLayer.Ets
  end

  test "T02 Reading attributes have the required names and types" do
    types =
      for name <- [
            :external_id,
            :meter_code,
            :raw_kwh,
            :net_kwh,
            :recorded_on,
            :batch_ref,
            :status
          ],
          into: %{} do
        attr = Ash.Resource.Info.attribute(Reading, name)
        assert attr, "Reading is missing attribute #{inspect(name)}"
        {name, attr.type}
      end

    assert types[:external_id] == Ash.Type.String
    assert types[:meter_code] == Ash.Type.String
    assert types[:raw_kwh] == Ash.Type.Integer
    assert types[:net_kwh] == Ash.Type.Integer
    assert types[:recorded_on] == Ash.Type.Date
    assert types[:batch_ref] == Ash.Type.String
    assert types[:status] == Ash.Type.Atom
  end

  test "T03 MeterRollup is keyed by meter_code and has the rollup counters" do
    assert Ash.Resource.Info.primary_key(MeterRollup) == [:meter_code]

    for name <- [:total_net_kwh, :reading_count, :revision] do
      attr = Ash.Resource.Info.attribute(MeterRollup, name)
      assert attr, "MeterRollup is missing attribute #{inspect(name)}"
      assert attr.type == Ash.Type.Integer
    end

    assert Ash.Resource.Info.attribute(MeterRollup, :last_batch_ref).type == Ash.Type.String
  end

  test "T04 Store.reset!/0 removes every persisted record" do
    H.ingest([H.row("A1", "M-ALPHA", 5)], "B-RESET")
    assert length(H.readings()) == 1
    assert Ingest.Pipeline.Store.reset!() == :ok
    assert H.readings() == []
    assert Ash.read!(Meter) == []
    assert H.rollups() == []
  end

  # -------------------------------------------------------------------- ingest

  test "T05 a clean batch is fully inserted and reported" do
    rows = [
      H.row("A1", "M-ALPHA", 10),
      H.row("A2", "M-BETA", 20),
      H.row("A3", "M-GAMMA", 30)
    ]

    report = H.ingest(rows, "B-1")

    assert Enum.sort(Map.keys(report)) == [
             :batch_ref,
             :failed,
             :inserted,
             :inserted_external_ids,
             :skipped,
             :status
           ]

    assert report.batch_ref == "B-1"
    assert report.status == :success
    assert report.inserted == 3
    assert report.skipped == 0
    assert report.failed == []
    assert report.inserted_external_ids == ["A1", "A2", "A3"]

    stored = H.readings()
    assert Enum.map(stored, & &1.external_id) == ["A1", "A2", "A3"]
    assert Enum.all?(stored, &(&1.status == :pending))
    assert Enum.all?(stored, &(&1.batch_ref == "B-1"))
    assert Enum.all?(stored, &is_nil(&1.net_kwh))
    assert Enum.map(stored, & &1.raw_kwh) == [10, 20, 30]
  end

  test "T06 a negative reading fails with its input index while the rest are written" do
    rows = [
      H.row("A1", "M-ALPHA", 10),
      H.row("A2", "M-BETA", 20),
      H.row("A3", "M-GAMMA", -1),
      H.row("A4", "M-ALPHA", 40)
    ]

    report = H.ingest(rows, "B-2")

    assert report.status == :partial_success
    assert report.inserted == 3
    assert report.skipped == 0
    assert report.failed == [%{index: 2, external_id: "A3", reason: :negative_raw_kwh}]
    assert report.inserted_external_ids == ["A1", "A2", "A4"]
    assert Enum.map(H.readings(), & &1.external_id) == ["A1", "A2", "A4"]
  end

  test "T07 rows with a missing or nil required value are reported as :missing_field" do
    rows = [
      H.row("A1", "M-ALPHA", 10),
      Map.delete(H.row("A2", "M-BETA", 20), :meter_code),
      %{H.row("A3", "M-GAMMA", 30) | external_id: nil},
      Map.put(H.row("A4", "M-ALPHA", 40), :raw_kwh, nil),
      H.row("A5", "M-ALPHA", 50)
    ]

    report = H.ingest(rows, "B-3")

    assert report.status == :partial_success
    assert report.inserted == 2

    assert report.failed == [
             %{index: 1, external_id: "A2", reason: :missing_field},
             %{index: 2, external_id: nil, reason: :missing_field},
             %{index: 3, external_id: "A4", reason: :missing_field}
           ]

    assert report.inserted_external_ids == ["A1", "A5"]
  end

  test "T08 repeated external ids inside one call keep the first row only" do
    rows = [
      H.row("A1", "M-ALPHA", 10),
      H.row("A2", "M-BETA", 20),
      H.row("A1", "M-GAMMA", 30),
      H.row("A2", "M-ALPHA", 40),
      H.row("A1", "M-ALPHA", 50)
    ]

    report = H.ingest(rows, "B-4")

    assert report.status == :partial_success
    assert report.inserted == 2

    assert report.failed == [
             %{index: 2, external_id: "A1", reason: :duplicate_in_batch},
             %{index: 3, external_id: "A2", reason: :duplicate_in_batch},
             %{index: 4, external_id: "A1", reason: :duplicate_in_batch}
           ]

    assert Enum.map(H.readings(), &{&1.external_id, &1.raw_kwh}) == [{"A1", 10}, {"A2", 20}]
  end

  test "T09 failure reasons follow the stated precedence" do
    rows = [
      H.row("A1", "M-ALPHA", 10),
      Map.put(H.row("A1", "M-ALPHA", -5), :recorded_on, nil),
      H.row("A1", "M-ALPHA", -7),
      H.row("A2", "M-ALPHA", 20)
    ]

    report = H.ingest(rows, "B-5")

    assert report.failed == [
             %{index: 1, external_id: "A1", reason: :missing_field},
             %{index: 2, external_id: "A1", reason: :negative_raw_kwh}
           ]

    assert report.inserted_external_ids == ["A1", "A2"]
  end

  test "T10 re-ingesting an identical batch inserts nothing and skips everything" do
    rows = [
      H.row("A1", "M-ALPHA", 10),
      H.row("A2", "M-BETA", 20),
      H.row("A3", "M-GAMMA", 30)
    ]

    H.ingest(rows, "B-6")
    report = H.ingest(rows, "B-7")

    assert report.status == :success
    assert report.inserted == 0
    assert report.skipped == 3
    assert report.failed == []
    assert report.inserted_external_ids == []
    assert length(H.readings()) == 3
    assert Enum.all?(H.readings(), &(&1.batch_ref == "B-6"))
  end

  test "T11 a known external id is never overwritten by a later batch" do
    H.ingest([H.row("A1", "M-ALPHA", 10)], "B-8")
    report = H.ingest([Map.put(H.row("A1", "M-BETA", 999), :recorded_on, ~D[2026-12-31])], "B-9")

    assert report.skipped == 1
    assert report.inserted == 0

    stored = H.by_eid("A1")
    assert stored.raw_kwh == 10
    assert stored.meter_code == "M-ALPHA"
    assert stored.batch_ref == "B-8"
    assert length(H.readings()) == 1
  end

  test "T12 new, known and invalid rows are counted separately in one call" do
    H.ingest([H.row("A1", "M-ALPHA", 10), H.row("A2", "M-BETA", 20)], "B-10")

    rows = [
      H.row("A1", "M-ALPHA", 10),
      H.row("A3", "M-GAMMA", 30),
      H.row("A4", "M-ALPHA", -2),
      H.row("A2", "M-BETA", 20),
      H.row("A5", "M-BETA", 50)
    ]

    report = H.ingest(rows, "B-11")

    assert report.status == :partial_success
    assert report.inserted == 2
    assert report.skipped == 2
    assert report.failed == [%{index: 2, external_id: "A4", reason: :negative_raw_kwh}]
    assert report.inserted_external_ids == ["A3", "A5"]
    assert length(H.readings()) == 4
  end

  test "T13 a batch in which every row fails reports :error" do
    rows = [
      H.row("A1", "M-ALPHA", -1),
      Map.delete(H.row("A2", "M-BETA", 20), :external_id)
    ]

    report = H.ingest(rows, "B-12")

    assert report.status == :error
    assert report.inserted == 0
    assert report.skipped == 0
    assert length(report.failed) == 2
    assert H.readings() == []
  end

  test "T14 an empty input list is a successful no-op" do
    report = H.ingest([], "B-13")

    assert report.status == :success
    assert report.inserted == 0
    assert report.skipped == 0
    assert report.failed == []
    assert report.inserted_external_ids == []
    assert H.readings() == []
  end

  test "T15 inserted ids keep input order across several batches" do
    rows = for i <- 1..10, do: H.row("A#{i}", "M-ALPHA", i)
    report = H.ingest(rows, "B-14", batch_size: 3)

    assert report.status == :success
    assert report.inserted == 10
    assert report.inserted_external_ids == Enum.map(1..10, &"A#{&1}")
  end

  test "T16 the ingest action itself rejects a negative reading" do
    assert {:error, error} =
             Ash.create(
               Reading,
               %{
                 external_id: "A1",
                 meter_code: "M-ALPHA",
                 raw_kwh: -3,
                 recorded_on: ~D[2026-03-02],
                 batch_ref: "B-15"
               },
               action: :ingest
             )

    assert %Ash.Error.Invalid{} = error
    assert :raw_kwh in H.error_fields(error)
    assert H.readings() == []
  end

  test "T17 the ingest action itself rejects a duplicate external id" do
    params = %{
      external_id: "A1",
      meter_code: "M-ALPHA",
      raw_kwh: 3,
      recorded_on: ~D[2026-03-02],
      batch_ref: "B-16"
    }

    assert {:ok, _} = Ash.create(Reading, params, action: :ingest)
    assert {:error, error} = Ash.create(Reading, %{params | raw_kwh: 9}, action: :ingest)
    assert %Ash.Error.Invalid{} = error
    assert :external_id in H.error_fields(error)
    assert length(H.readings()) == 1
  end

  # ------------------------------------------------------------- ingest_stream

  test "T18 ingest_stream/3 writes nothing until it is consumed" do
    rows = for i <- 1..100, do: H.row("S#{i}", "M-ALPHA", i)
    stream = Ingest.Pipeline.Ingestion.ingest_stream(rows, "B-17", batch_size: 10)

    assert Ash.count!(Reading) == 0

    taken = Enum.take(stream, 5)
    assert length(taken) == 5
    assert Enum.all?(taken, &match?({:ok, _}, &1))
    assert Ash.count!(Reading) == 10
  end

  test "T19 ingest_stream/3 emits results and input indices in input order" do
    rows = [
      H.row("S1", "M-ALPHA", 1),
      H.row("S2", "M-BETA", -1),
      H.row("S3", "M-GAMMA", 3),
      Map.delete(H.row("S4", "M-ALPHA", 4), :meter_code),
      H.row("S5", "M-ALPHA", 5)
    ]

    elements =
      rows
      |> Ingest.Pipeline.Ingestion.ingest_stream("B-18", batch_size: 2)
      |> Enum.to_list()

    tags =
      Enum.map(elements, fn
        {:ok, record} -> {:ok, record.external_id}
        other -> other
      end)

    assert tags == [{:ok, "S1"}, {:error, 1}, {:ok, "S3"}, {:error, 3}, {:ok, "S5"}]
    assert Enum.map(H.readings(), & &1.external_id) == ["S1", "S3", "S5"]
    assert Enum.all?(H.readings(), &(&1.batch_ref == "B-18"))
  end

  # ------------------------------------------------------------ pending_stream

  test "T20 pending_stream/1 pages through the data layer" do
    for i <- 1..2400 do
      H.seed_reading!(%{external_id: "P#{i}", meter_code: "M-ALPHA", raw_kwh: 1})
    end

    {records, reads} =
      H.count_reads(Reading, fn ->
        Ingest.Pipeline.Ingestion.pending_stream(batch_size: 300) |> Enum.to_list()
      end)

    assert length(records) == 2400
    assert Enum.all?(records, &is_struct(&1, Reading))
    assert reads >= 8, "expected paged reads, got #{reads}"
    assert reads <= 10, "expected at most 10 reads for 2400 records, got #{reads}"
  end

  test "T21 pending_stream/1 is lazy" do
    for i <- 1..2400 do
      H.seed_reading!(%{external_id: "P#{i}", meter_code: "M-ALPHA", raw_kwh: 1})
    end

    {taken, reads} =
      H.count_reads(Reading, fn ->
        Ingest.Pipeline.Ingestion.pending_stream(batch_size: 300) |> Enum.take(3)
      end)

    assert length(taken) == 3
    assert reads <= 2, "taking 3 records should not read the whole table (#{reads} reads)"
  end

  test "T22 pending_stream/1 only yields pending readings" do
    H.seed_reading!(%{external_id: "P1", meter_code: "M-ALPHA", raw_kwh: 1, status: :pending})
    H.seed_reading!(%{external_id: "P2", meter_code: "M-ALPHA", raw_kwh: 2, status: :normalized})
    H.seed_reading!(%{external_id: "P3", meter_code: "M-ALPHA", raw_kwh: 3, status: :accepted})
    H.seed_reading!(%{external_id: "P4", meter_code: "M-ALPHA", raw_kwh: 4, status: :rejected})
    H.seed_reading!(%{external_id: "P5", meter_code: "M-ALPHA", raw_kwh: 5, status: :pending})

    ids =
      Ingest.Pipeline.Ingestion.pending_stream()
      |> Enum.map(& &1.external_id)
      |> Enum.sort()

    assert ids == ["P1", "P5"]
  end

  # ----------------------------------------------------------------- reconcile

  test "T23 reconcile/1 normalizes, accepts and reports the pass" do
    rows = [
      H.row("A1", "M-ALPHA", 40),
      H.row("A2", "M-BETA", 40),
      H.row("A3", "M-GAMMA", 10)
    ]

    H.ingest(rows, "B-20")
    report = Ingest.Pipeline.Ingestion.reconcile("B-20")

    assert Enum.sort(Map.keys(report)) == [:accepted, :batch_ref, :normalized, :rejected]
    assert report.batch_ref == "B-20"
    assert report.normalized == 3
    assert report.rejected == 0
    assert report.accepted == 3

    assert Enum.map(H.readings(), &{&1.external_id, &1.status, &1.net_kwh}) == [
             {"A1", :accepted, 40},
             {"A2", :accepted, 50},
             {"A3", :accepted, 10}
           ]
  end

  test "T24 normalisation rounds halves up" do
    rows = [
      H.row("A1", "M-BETA", 2),
      H.row("A2", "M-GAMMA", 3),
      H.row("A3", "M-GAMMA", 7)
    ]

    H.ingest(rows, "B-21")
    Ingest.Pipeline.Ingestion.reconcile("B-21")

    assert Enum.map(H.readings(), &{&1.external_id, &1.net_kwh}) == [
             {"A1", 3},
             {"A2", 3},
             {"A3", 7}
           ]
  end

  test "T25 readings for unknown or inactive meters are rejected" do
    rows = [
      H.row("A1", "M-ALPHA", 10),
      H.row("A2", "M-NONE", 20),
      H.row("A3", "M-OFF", 30)
    ]

    H.ingest(rows, "B-22")
    report = Ingest.Pipeline.Ingestion.reconcile("B-22")

    assert report.normalized == 1
    assert report.rejected == 2
    assert report.accepted == 1

    assert Enum.map(H.readings(), &{&1.external_id, &1.status, &1.net_kwh}) == [
             {"A1", :accepted, 10},
             {"A2", :rejected, nil},
             {"A3", :rejected, nil}
           ]
  end

  test "T26 reconcile/1 builds one rollup row per meter" do
    rows = [
      H.row("A1", "M-ALPHA", 10),
      H.row("A2", "M-ALPHA", 30),
      H.row("A3", "M-BETA", 40),
      H.row("A4", "M-NONE", 50)
    ]

    H.ingest(rows, "B-23")
    Ingest.Pipeline.Ingestion.reconcile("B-23")

    assert Enum.map(
             H.rollups(),
             &{&1.meter_code, &1.total_net_kwh, &1.reading_count, &1.last_batch_ref, &1.revision}
           ) == [
             {"M-ALPHA", 40, 2, "B-23", 1},
             {"M-BETA", 50, 1, "B-23", 1}
           ]
  end

  test "T27 a second batch accumulates into the existing rollup" do
    H.ingest([H.row("A1", "M-ALPHA", 10), H.row("A2", "M-BETA", 40)], "B-24")
    Ingest.Pipeline.Ingestion.reconcile("B-24")

    H.ingest([H.row("A3", "M-ALPHA", 5), H.row("A4", "M-ALPHA", 7)], "B-25")
    report = Ingest.Pipeline.Ingestion.reconcile("B-25")

    assert report.accepted == 2

    alpha = H.rollup_for("M-ALPHA")
    assert alpha.total_net_kwh == 22
    assert alpha.reading_count == 3
    assert alpha.last_batch_ref == "B-25"
    assert alpha.revision == 2

    beta = H.rollup_for("M-BETA")
    assert beta.total_net_kwh == 50
    assert beta.reading_count == 1
    assert beta.last_batch_ref == "B-24"
    assert beta.revision == 1

    assert length(H.rollups()) == 2
  end

  test "T28 re-running reconcile/1 for the same batch changes nothing" do
    H.ingest([H.row("A1", "M-ALPHA", 10), H.row("A2", "M-NONE", 20)], "B-26")
    Ingest.Pipeline.Ingestion.reconcile("B-26")

    before_rollups =
      Enum.map(H.rollups(), &{&1.meter_code, &1.total_net_kwh, &1.reading_count, &1.revision})

    report = Ingest.Pipeline.Ingestion.reconcile("B-26")

    assert report.normalized == 0
    assert report.rejected == 0
    assert report.accepted == 0

    assert Enum.map(H.rollups(), &{&1.meter_code, &1.total_net_kwh, &1.reading_count, &1.revision}) ==
             before_rollups

    assert Enum.map(H.readings(), &{&1.external_id, &1.status}) == [
             {"A1", :accepted},
             {"A2", :rejected}
           ]
  end

  test "T29 reconcile/1 leaves other batches untouched" do
    H.ingest([H.row("A1", "M-ALPHA", 10)], "B-27")
    H.ingest([H.row("B1", "M-BETA", 40)], "B-28")

    report = Ingest.Pipeline.Ingestion.reconcile("B-27")
    assert report.accepted == 1

    assert Enum.map(H.readings(), &{&1.external_id, &1.status}) == [
             {"A1", :accepted},
             {"B1", :pending}
           ]

    assert Enum.map(H.rollups(), & &1.meter_code) == ["M-ALPHA"]
  end

  test "T30 a rejected batch produces no rollup at all" do
    H.ingest([H.row("A1", "M-NONE", 10), H.row("A2", "M-OFF", 20)], "B-29")
    report = Ingest.Pipeline.Ingestion.reconcile("B-29")

    assert report.normalized == 0
    assert report.rejected == 2
    assert report.accepted == 0
    assert H.rollups() == []
  end

  # ------------------------------------------------------------------- purging

  test "T31 purge_rejected/1 destroys only the rejected rows of its batch" do
    H.ingest([H.row("A1", "M-ALPHA", 10), H.row("A2", "M-NONE", 20), H.row("A3", "M-OFF", 30)], "B-30")
    H.ingest([H.row("B1", "M-NONE", 40)], "B-31")
    Ingest.Pipeline.Ingestion.reconcile("B-30")
    Ingest.Pipeline.Ingestion.reconcile("B-31")

    assert Ingest.Pipeline.Ingestion.purge_rejected("B-30") == 2

    assert Enum.map(H.readings(), &{&1.external_id, &1.status}) == [
             {"A1", :accepted},
             {"B1", :rejected}
           ]
  end

  test "T32 purge_rejected/1 returns zero when there is nothing to purge" do
    H.ingest([H.row("A1", "M-ALPHA", 10)], "B-32")
    Ingest.Pipeline.Ingestion.reconcile("B-32")

    assert Ingest.Pipeline.Ingestion.purge_rejected("B-32") == 0
    assert length(H.readings()) == 1
  end

  # ---------------------------------------------------------------- strategies

  defp seed_mixed_batch!(pending_positions \\ [1]) do
    for i <- 1..6 do
      status = if i in pending_positions, do: :pending, else: :normalized

      H.seed_reading!(%{
        external_id: "R#{i}",
        meter_code: "M-ALPHA",
        raw_kwh: i,
        net_kwh: i,
        batch_ref: "B-STRAT",
        status: status
      })
    end

    :ok
  end

  test "T33 the accept action is declared fully atomic" do
    assert Ash.Resource.Info.action(Reading, :accept).require_atomic? == true
    assert Ash.Resource.Info.action(Reading, :normalize).require_atomic? == false
  end

  test "T34 an atomic bulk accept over a clean query succeeds" do
    for i <- 1..4 do
      H.seed_reading!(%{
        external_id: "R#{i}",
        meter_code: "M-ALPHA",
        raw_kwh: i,
        net_kwh: i,
        batch_ref: "B-STRAT",
        status: :normalized
      })
    end

    result =
      Reading
      |> Ash.Query.filter(batch_ref == "B-STRAT")
      |> Ash.bulk_update(:accept, %{},
        strategy: [:atomic],
        return_records?: true,
        return_errors?: true
      )

    assert %Ash.BulkResult{status: :success, error_count: 0} = result
    assert length(result.records) == 4
    assert Enum.all?(H.readings(), &(&1.status == :accepted))
  end

  test "T35 an atomic bulk accept is all-or-nothing when one row is not normalized" do
    seed_mixed_batch!([1])

    result =
      Reading
      |> Ash.Query.filter(batch_ref == "B-STRAT")
      |> Ash.Query.sort(external_id: :asc)
      |> Ash.bulk_update(:accept, %{},
        strategy: [:atomic],
        return_records?: true,
        return_errors?: true
      )

    assert result.status == :error
    assert result.error_count == 1
    assert :status in H.error_fields(%{errors: result.errors})

    assert Enum.map(H.readings(), &{&1.external_id, &1.status}) == [
             {"R1", :pending},
             {"R2", :normalized},
             {"R3", :normalized},
             {"R4", :normalized},
             {"R5", :normalized},
             {"R6", :normalized}
           ]
  end

  test "T36 the stream strategy accepts every valid row of the same query" do
    seed_mixed_batch!([1])

    result =
      Reading
      |> Ash.Query.filter(batch_ref == "B-STRAT")
      |> Ash.Query.sort(external_id: :asc)
      |> Ash.bulk_update(:accept, %{},
        strategy: [:stream],
        return_records?: true,
        return_errors?: true,
        stop_on_error?: false
      )

    assert result.status == :partial_success
    assert result.error_count == 1
    assert length(result.records) == 5

    assert Enum.map(H.readings(), &{&1.external_id, &1.status}) == [
             {"R1", :pending},
             {"R2", :accepted},
             {"R3", :accepted},
             {"R4", :accepted},
             {"R5", :accepted},
             {"R6", :accepted}
           ]
  end

  test "T37 atomic batches only lose the batch that contains a bad row" do
    seed_mixed_batch!([3, 4])
    records = H.readings()

    result =
      Ash.bulk_update(records, :accept, %{},
        strategy: [:atomic_batches],
        batch_size: 2,
        return_records?: true,
        return_errors?: true,
        stop_on_error?: false
      )

    assert result.status == :partial_success
    assert length(result.records) == 4
    assert result.error_count >= 1

    assert Enum.map(H.readings(), &{&1.external_id, &1.status}) == [
             {"R1", :accepted},
             {"R2", :accepted},
             {"R3", :pending},
             {"R4", :pending},
             {"R5", :accepted},
             {"R6", :accepted}
           ]
  end

  test "T38 accepting a reading that is not normalized fails on :status" do
    H.seed_reading!(%{
      external_id: "R1",
      meter_code: "M-ALPHA",
      raw_kwh: 1,
      batch_ref: "B-STRAT",
      status: :pending
    })

    record = H.by_eid("R1")
    assert {:error, error} = Ash.update(record, %{}, action: :accept)
    assert :status in H.error_fields(error)
    assert H.by_eid("R1").status == :pending
  end

  test "T39 the normalize action cannot be forced onto the atomic strategy" do
    H.ingest([H.row("A1", "M-ALPHA", 10)], "B-33")

    result =
      Reading
      |> Ash.Query.filter(batch_ref == "B-33")
      |> Ash.bulk_update(:normalize, %{}, strategy: [:atomic], return_errors?: true)

    assert result.status == :error
    assert H.by_eid("A1").status == :pending
  end

  test "T40 the stream strategy applies each meter's own factor" do
    H.ingest(
      [
        H.row("A1", "M-ALPHA", 40),
        H.row("A2", "M-BETA", 40),
        H.row("A3", "M-GAMMA", 40)
      ],
      "B-34"
    )

    result =
      Reading
      |> Ash.Query.filter(batch_ref == "B-34")
      |> Ash.bulk_update(:normalize, %{},
        strategy: [:stream],
        return_records?: true,
        return_errors?: true
      )

    assert result.status == :success

    assert Enum.map(H.readings(), &{&1.external_id, &1.net_kwh, &1.status}) == [
             {"A1", 40, :normalized},
             {"A2", 50, :normalized},
             {"A3", 38, :normalized}
           ]
  end
end

ExUnit.run()
"""


def _tail(text, limit=6000):
    text = text or ""
    return text[-limit:]


@pytest.fixture(scope="session")
def suite_run():
    with open(SUITE_PATH, "w", encoding="utf-8") as handle:
        handle.write(SUITE_SOURCE.lstrip("\n"))

    env = dict(os.environ)
    env["MIX_ENV"] = "dev"
    env.setdefault("HEX_OFFLINE", "1")

    try:
        proc = subprocess.run(
            ["mix", "run", SUITE_PATH],
            cwd=PROJECT_DIR,
            env=env,
            capture_output=True,
            text=True,
            timeout=1800,
        )
    except subprocess.TimeoutExpired as exc:
        pytest.fail(f"The verification suite timed out after 1800s: {exc}")

    results = {}
    for line in proc.stdout.splitlines():
        if not line.startswith(MARKER):
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

    if not results:
        pytest.fail(
            "The ExUnit verification suite produced no results. The project most likely "
            "failed to compile.\n"
            f"exit code: {proc.returncode}\n"
            f"STDOUT tail:\n{_tail(proc.stdout)}\n"
            f"STDERR tail:\n{_tail(proc.stderr)}"
        )

    return {"results": results, "stdout": proc.stdout, "stderr": proc.stderr}


def _scenario(suite_run, scenario_id):
    results = suite_run["results"]
    prefix = f"test {scenario_id} "
    matches = [name for name in results if name.startswith(prefix)]
    assert matches, (
        f"Scenario {scenario_id} did not run.\n"
        f"STDOUT tail:\n{_tail(suite_run['stdout'])}\n"
        f"STDERR tail:\n{_tail(suite_run['stderr'])}"
    )
    status, detail = results[matches[0]]
    assert status == "passed", f"Scenario {scenario_id} failed:\n{detail}"


def test_t01_reading_and_meterrollup_are_ets_backed_resources_of_the(suite_run):
    _scenario(suite_run, "T01")


def test_t02_reading_attributes_have_the_required_names_and_types(suite_run):
    _scenario(suite_run, "T02")


def test_t03_meterrollup_is_keyed_by_meter_code_and_has_the(suite_run):
    _scenario(suite_run, "T03")


def test_t04_store_reset_0_removes_every_persisted_record(suite_run):
    _scenario(suite_run, "T04")


def test_t05_a_clean_batch_is_fully_inserted_and_reported(suite_run):
    _scenario(suite_run, "T05")


def test_t06_a_negative_reading_fails_with_its_input_index_while(suite_run):
    _scenario(suite_run, "T06")


def test_t07_rows_with_a_missing_or_nil_required_value_are(suite_run):
    _scenario(suite_run, "T07")


def test_t08_repeated_external_ids_inside_one_call_keep_the_first(suite_run):
    _scenario(suite_run, "T08")


def test_t09_failure_reasons_follow_the_stated_precedence(suite_run):
    _scenario(suite_run, "T09")


def test_t10_re_ingesting_an_identical_batch_inserts_nothing_and_skips(suite_run):
    _scenario(suite_run, "T10")


def test_t11_a_known_external_id_is_never_overwritten_by_a(suite_run):
    _scenario(suite_run, "T11")


def test_t12_new_known_and_invalid_rows_are_counted_separately_in(suite_run):
    _scenario(suite_run, "T12")


def test_t13_a_batch_in_which_every_row_fails_reports_error(suite_run):
    _scenario(suite_run, "T13")


def test_t14_an_empty_input_list_is_a_successful_no_op(suite_run):
    _scenario(suite_run, "T14")


def test_t15_inserted_ids_keep_input_order_across_several_batches(suite_run):
    _scenario(suite_run, "T15")


def test_t16_the_ingest_action_itself_rejects_a_negative_reading(suite_run):
    _scenario(suite_run, "T16")


def test_t17_the_ingest_action_itself_rejects_a_duplicate_external_id(suite_run):
    _scenario(suite_run, "T17")


def test_t18_ingest_stream_3_writes_nothing_until_it_is_consumed(suite_run):
    _scenario(suite_run, "T18")


def test_t19_ingest_stream_3_emits_results_and_input_indices_in(suite_run):
    _scenario(suite_run, "T19")


def test_t20_pending_stream_1_pages_through_the_data_layer(suite_run):
    _scenario(suite_run, "T20")


def test_t21_pending_stream_1_is_lazy(suite_run):
    _scenario(suite_run, "T21")


def test_t22_pending_stream_1_only_yields_pending_readings(suite_run):
    _scenario(suite_run, "T22")


def test_t23_reconcile_1_normalizes_accepts_and_reports_the_pass(suite_run):
    _scenario(suite_run, "T23")


def test_t24_normalisation_rounds_halves_up(suite_run):
    _scenario(suite_run, "T24")


def test_t25_readings_for_unknown_or_inactive_meters_are_rejected(suite_run):
    _scenario(suite_run, "T25")


def test_t26_reconcile_1_builds_one_rollup_row_per_meter(suite_run):
    _scenario(suite_run, "T26")


def test_t27_a_second_batch_accumulates_into_the_existing_rollup(suite_run):
    _scenario(suite_run, "T27")


def test_t28_re_running_reconcile_1_for_the_same_batch_changes(suite_run):
    _scenario(suite_run, "T28")


def test_t29_reconcile_1_leaves_other_batches_untouched(suite_run):
    _scenario(suite_run, "T29")


def test_t30_a_rejected_batch_produces_no_rollup_at_all(suite_run):
    _scenario(suite_run, "T30")


def test_t31_purge_rejected_1_destroys_only_the_rejected_rows_of(suite_run):
    _scenario(suite_run, "T31")


def test_t32_purge_rejected_1_returns_zero_when_there_is_nothing(suite_run):
    _scenario(suite_run, "T32")


def test_t33_the_accept_action_is_declared_fully_atomic(suite_run):
    _scenario(suite_run, "T33")


def test_t34_an_atomic_bulk_accept_over_a_clean_query_succeeds(suite_run):
    _scenario(suite_run, "T34")


def test_t35_an_atomic_bulk_accept_is_all_or_nothing_when(suite_run):
    _scenario(suite_run, "T35")


def test_t36_the_stream_strategy_accepts_every_valid_row_of_the(suite_run):
    _scenario(suite_run, "T36")


def test_t37_atomic_batches_only_lose_the_batch_that_contains_a(suite_run):
    _scenario(suite_run, "T37")


def test_t38_accepting_a_reading_that_is_not_normalized_fails_on(suite_run):
    _scenario(suite_run, "T38")


def test_t39_the_normalize_action_cannot_be_forced_onto_the_atomic(suite_run):
    _scenario(suite_run, "T39")


def test_t40_the_stream_strategy_applies_each_meter_s_own_factor(suite_run):
    _scenario(suite_run, "T40")
