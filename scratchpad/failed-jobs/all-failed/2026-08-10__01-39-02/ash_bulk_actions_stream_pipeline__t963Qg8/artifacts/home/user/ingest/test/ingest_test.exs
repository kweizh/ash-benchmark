defmodule Ingest.PipelineTest do
  use ExUnit.Case, async: false

  require Ash.Query

  alias Ingest.Pipeline.Meter
  alias Ingest.Pipeline.Reading
  alias Ingest.Pipeline.MeterRollup
  alias Ingest.Pipeline.Store
  alias Ingest.Pipeline.Ingestion

  setup do
    # Reset store before each test
    Store.reset!()
    :ok
  end

  test "Reading: basic attribute validations and ingest action" do
    # Create a valid reading
    {:ok, reading} =
      Reading
      |> Ash.Changeset.for_create(:ingest, %{
        external_id: "ext_1",
        meter_code: "M1",
        raw_kwh: 100,
        recorded_on: ~D[2026-08-01],
        batch_ref: "batch_A"
      })
      |> Ash.create()

    assert reading.external_id == "ext_1"
    assert reading.status == :pending
    assert reading.net_kwh == nil

    # Negative raw_kwh should fail with Ash.Error.Invalid reporting field :raw_kwh
    res =
      Reading
      |> Ash.Changeset.for_create(:ingest, %{
        external_id: "ext_2",
        meter_code: "M1",
        raw_kwh: -5,
        recorded_on: ~D[2026-08-01],
        batch_ref: "batch_A"
      })
      |> Ash.create()

    assert {:error, %Ash.Error.Invalid{errors: errors}} = res

    assert Enum.any?(errors, fn err ->
             Map.get(err, :field) == :raw_kwh or Map.get(err, :fields) == [:raw_kwh]
           end)

    # Duplicate external_id should fail with Ash.Error.Invalid reporting field :external_id
    res_dup =
      Reading
      |> Ash.Changeset.for_create(:ingest, %{
        external_id: "ext_1",
        meter_code: "M2",
        raw_kwh: 50,
        recorded_on: ~D[2026-08-01],
        batch_ref: "batch_A"
      })
      |> Ash.create()

    assert {:error, %Ash.Error.Invalid{errors: errors_dup}} = res_dup

    assert Enum.any?(errors_dup, fn err ->
             Map.get(err, :field) == :external_id or Map.get(err, :fields) == [:external_id]
           end)
  end

  test "Reading: normalize action is not atomic" do
    # Verify normalize is not atomically executable
    # Set up a meter
    Meter
    |> Ash.Changeset.for_create(:create, %{
      code: "M1",
      scale_bp: 10_000,
      active: true
    })
    |> Ash.create!()

    # Create a pending reading
    _reading =
      Reading
      |> Ash.Changeset.for_create(:ingest, %{
        external_id: "ext_1",
        meter_code: "M1",
        raw_kwh: 100,
        recorded_on: ~D[2026-08-01],
        batch_ref: "batch_A"
      })
      |> Ash.create!()

    # Forcing bulk update to use atomic strategy should fail
    query = Ash.Query.filter(Reading, external_id == "ext_1")

    res = Ash.bulk_update(query, :normalize, %{}, strategy: :atomic)
    assert %Ash.BulkResult{status: :error} = res
  end

  test "Reading: accept action is fully atomic and validates status" do
    # Create a reading with status :pending
    reading =
      Reading
      |> Ash.Changeset.for_create(:ingest, %{
        external_id: "ext_1",
        meter_code: "M1",
        raw_kwh: 100,
        recorded_on: ~D[2026-08-01],
        batch_ref: "batch_A"
      })
      |> Ash.create!()

    # Accepting a pending reading should fail with status error
    res =
      reading
      |> Ash.Changeset.for_update(:accept, %{})
      |> Ash.update()

    assert {:error, %Ash.Error.Invalid{errors: errors}} = res

    assert Enum.any?(errors, fn err ->
             Map.get(err, :field) == :status or Map.get(err, :fields) == [:status]
           end)

    # Change status to :normalized manually (since normalize is non-atomic)
    normalized_reading =
      reading
      |> Ash.Changeset.for_update(:update, %{status: :normalized})
      |> Ash.update!()

    # Now accepting it should succeed
    accepted_reading =
      normalized_reading
      |> Ash.Changeset.for_update(:accept, %{})
      |> Ash.update!()

    assert accepted_reading.status == :accepted
  end

  test "Ingestion: eager ingest/3" do
    # Setup some pre-existing readings
    Reading
    |> Ash.Changeset.for_create(:ingest, %{
      external_id: "already_stored",
      meter_code: "M1",
      raw_kwh: 50,
      recorded_on: ~D[2026-08-01],
      batch_ref: "batch_old"
    })
    |> Ash.create!()

    rows = [
      # Sound row
      %{external_id: "ext_1", meter_code: "M1", raw_kwh: 100, recorded_on: ~D[2026-08-01]},
      # Missing field
      %{external_id: "ext_2", meter_code: nil, raw_kwh: 100, recorded_on: ~D[2026-08-01]},
      # Negative raw_kwh
      %{external_id: "ext_3", meter_code: "M1", raw_kwh: -10, recorded_on: ~D[2026-08-01]},
      # Duplicate in batch
      %{external_id: "ext_1", meter_code: "M1", raw_kwh: 120, recorded_on: ~D[2026-08-01]},
      # Skipped row (already stored)
      %{
        external_id: "already_stored",
        meter_code: "M1",
        raw_kwh: 200,
        recorded_on: ~D[2026-08-01]
      }
    ]

    res = Ingestion.ingest(rows, "batch_new", batch_size: 2)

    assert res.batch_ref == "batch_new"
    assert res.status == :partial_success
    assert res.inserted == 1
    assert res.skipped == 1
    assert length(res.failed) == 3

    # Check order and values of failed
    [f1, f2, f3] = res.failed
    assert f1.index == 1
    assert f1.reason == :missing_field

    assert f2.index == 2
    assert f2.reason == :negative_raw_kwh

    assert f3.index == 3
    assert f3.reason == :duplicate_in_batch

    assert res.inserted_external_ids == ["ext_1"]

    # Verify existing stored record was NOT touched
    stored = Ash.get!(Reading, "already_stored")
    assert stored.raw_kwh == 50
    assert stored.batch_ref == "batch_old"

    # Verify new reading was created
    new_r = Ash.get!(Reading, "ext_1")
    assert new_r.raw_kwh == 100
    assert new_r.batch_ref == "batch_new"
  end

  test "Ingestion: ingest_stream/3 is lazy and respects batch_size" do
    rows =
      Enum.map(1..100, fn i ->
        %{
          external_id: "ext_#{i}",
          meter_code: "M1",
          raw_kwh: i,
          recorded_on: ~D[2026-08-01]
        }
      end)

    stream = Ingestion.ingest_stream(rows, "batch_stream", batch_size: 10)

    # Before consuming, nothing should be stored
    assert Ash.read!(Reading).results == []

    # Demanding 5 elements should write exactly 10 readings (first batch of 10)
    taken = Enum.take(stream, 5)
    assert length(taken) == 5

    stored = Ash.read!(Reading).results
    assert length(stored) == 10

    # The taken elements should be the first 5 ok results
    assert Enum.all?(taken, fn elem -> match?({:ok, %Reading{}}, elem) end)
  end

  test "Ingestion: pending_stream/1 is lazy and paged" do
    # Create 2400 pending readings
    # To do this fast, we can use bulk_create
    inputs =
      Enum.map(1..2400, fn i ->
        %{
          external_id: "ext_#{i}",
          meter_code: "M1",
          raw_kwh: 10,
          recorded_on: ~D[2026-08-01],
          batch_ref: "batch_pending"
        }
      end)

    Ash.bulk_create!(inputs, Reading, :ingest, return_records?: false)

    # Check pending_stream with batch_size: 300
    stream = Ingestion.pending_stream(batch_size: 300)

    # Demanding only first 3 records should not pull all into memory
    first_3 = Enum.take(stream, 3)
    assert length(first_3) == 3

    # Consuming the whole stream should return 2400 records
    all = Enum.to_list(stream)
    assert length(all) == 2400
  end

  test "Reconciliation pipeline" do
    # Set up active and inactive meters
    # Meter 1: active, scale_bp = 12_000 (1.2)
    Meter
    |> Ash.Changeset.for_create(:create, %{code: "M1", scale_bp: 12_000, active: true})
    |> Ash.create!()

    # Meter 2: active, scale_bp = 8_500 (0.85)
    Meter
    |> Ash.Changeset.for_create(:create, %{code: "M2", scale_bp: 8_500, active: true})
    |> Ash.create!()

    # Meter 3: inactive
    Meter
    |> Ash.Changeset.for_create(:create, %{code: "M3", scale_bp: 10_000, active: false})
    |> Ash.create!()

    # Ingest some readings
    rows = [
      # M1: raw_kwh = 10 -> net_kwh = 10 * 12000 / 10000 = 12
      %{external_id: "r1", meter_code: "M1", raw_kwh: 10, recorded_on: ~D[2026-08-01]},
      # M1: raw_kwh = 15 -> net_kwh = 15 * 12000 / 10000 = 18
      %{external_id: "r2", meter_code: "M1", raw_kwh: 15, recorded_on: ~D[2026-08-01]},
      # M2: raw_kwh = 15 -> net_kwh = 15 * 8500 / 10000 = 12.75 -> rounded half up is 13
      %{external_id: "r3", meter_code: "M2", raw_kwh: 15, recorded_on: ~D[2026-08-01]},
      # M3: inactive -> rejected
      %{external_id: "r4", meter_code: "M3", raw_kwh: 100, recorded_on: ~D[2026-08-01]},
      # Non-existent meter -> rejected
      %{external_id: "r5", meter_code: "M_NONE", raw_kwh: 100, recorded_on: ~D[2026-08-01]}
    ]

    Ingestion.ingest(rows, "batch_recon")

    # Run reconcile
    recon_res = Ingestion.reconcile("batch_recon")

    assert recon_res.batch_ref == "batch_recon"
    # r1, r2, r3
    assert recon_res.normalized == 3
    # r4, r5
    assert recon_res.rejected == 2
    assert recon_res.accepted == 3

    # Verify reading states and net_kwh
    r1 = Ash.get!(Reading, "r1")
    assert r1.status == :accepted
    assert r1.net_kwh == 12

    r2 = Ash.get!(Reading, "r2")
    assert r2.status == :accepted
    assert r2.net_kwh == 18

    r3 = Ash.get!(Reading, "r3")
    assert r3.status == :accepted
    # 12.75 rounded half-up
    assert r3.net_kwh == 13

    r4 = Ash.get!(Reading, "r4")
    assert r4.status == :rejected
    assert r4.net_kwh == nil

    # Verify MeterRollup rows
    m1_rollup = Ash.get!(MeterRollup, "M1")
    # 12 + 18
    assert m1_rollup.total_net_kwh == 30
    assert m1_rollup.reading_count == 2
    assert m1_rollup.revision == 1
    assert m1_rollup.last_batch_ref == "batch_recon"

    m2_rollup = Ash.get!(MeterRollup, "M2")
    assert m2_rollup.total_net_kwh == 13
    assert m2_rollup.reading_count == 1
    assert m2_rollup.revision == 1
    assert m2_rollup.last_batch_ref == "batch_recon"

    # M3 should have no rollup
    assert {:error, _} = Ash.get(MeterRollup, "M3")

    # Running reconcile again should report zeros and leave everything unchanged
    recon_res2 = Ingestion.reconcile("batch_recon")
    assert recon_res2.normalized == 0
    assert recon_res2.rejected == 0
    assert recon_res2.accepted == 0

    m1_rollup_after = Ash.get!(MeterRollup, "M1")
    assert m1_rollup_after.total_net_kwh == 30
    assert m1_rollup_after.revision == 1
  end

  test "purge_rejected/1" do
    # Create some rejected and accepted readings
    Reading
    |> Ash.Changeset.for_create(:ingest, %{
      external_id: "r1",
      meter_code: "M1",
      raw_kwh: 10,
      recorded_on: ~D[2026-08-01],
      batch_ref: "b1"
    })
    |> Ash.create!()
    |> Ash.Changeset.for_update(:update, %{status: :rejected})
    |> Ash.update!()

    Reading
    |> Ash.Changeset.for_create(:ingest, %{
      external_id: "r2",
      meter_code: "M1",
      raw_kwh: 20,
      recorded_on: ~D[2026-08-01],
      batch_ref: "b1"
    })
    |> Ash.create!()
    |> Ash.Changeset.for_update(:update, %{status: :accepted})
    |> Ash.update!()

    Reading
    |> Ash.Changeset.for_create(:ingest, %{
      external_id: "r3",
      meter_code: "M1",
      raw_kwh: 30,
      recorded_on: ~D[2026-08-01],
      batch_ref: "b2"
    })
    |> Ash.create!()
    |> Ash.Changeset.for_update(:update, %{status: :rejected})
    |> Ash.update!()

    # Purge rejected for b1
    purged = Ingestion.purge_rejected("b1")
    assert purged == 1

    # r1 should be gone
    assert {:error, _} = Ash.get(Reading, "r1")
    # r2 (accepted) should still exist
    assert {:ok, _} = Ash.get(Reading, "r2")
    # r3 (rejected but in b2) should still exist
    assert {:ok, _} = Ash.get(Reading, "r3")
  end
end
