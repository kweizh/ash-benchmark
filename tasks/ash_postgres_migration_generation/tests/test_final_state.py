"""Final-state verification for the `ash_postgres_migration_generation` Harbor task.

The verifier boots the executor's Ash application for real:

* it starts the in-container PostgreSQL 16 server,
* compiles the project,
* asserts that `mix ash.codegen --check` reports nothing left to generate,
* rebuilds the whole database from the generated migrations with `mix ash.reset`,
* and finally runs an ExUnit suite (injected at `/tmp/harbor_pgmigrate_final.exs`)
  through `mix run`, which inspects the live PostgreSQL catalog and drives the
  domain through `Ash`.

The ExUnit suite prints one `@@HARBOR@@<name>@@<status>@@<base64 detail>` line per
scenario, so every behaviour is reported as its own pytest failure.
"""

import base64
import os
import subprocess

import pytest

PROJECT_DIR = "/home/user/logistics"
HARNESS_PATH = "/tmp/harbor_pgmigrate_final.exs"
MARKER = "@@HARBOR@@"

HARNESS_EXS = r'''
defmodule Harbor.Formatter do
  @moduledoc false
  use GenServer

  def init(_opts), do: {:ok, %{}}

  def handle_cast({:test_finished, %ExUnit.Test{} = test}, state) do
    {status, detail} =
      case test.state do
        nil ->
          {"pass", ""}

        {:failed, failures} ->
          {"fail",
           ExUnit.Formatter.format_test_failure(test, failures, 1, 200, fn _kind, msg -> msg end)}

        {:invalid, _} ->
          {"fail", "invalid test module (setup_all failed)"}

        {:skipped, reason} ->
          {"fail", "skipped: #{inspect(reason)}"}

        {:excluded, reason} ->
          {"fail", "excluded: #{inspect(reason)}"}
      end

    IO.puts("@@HARBOR@@#{test.name}@@#{status}@@#{Base.encode64(detail)}")
    {:noreply, state}
  end

  def handle_cast(_event, state), do: {:noreply, state}
end

defmodule Harbor.H do
  @moduledoc false

  def repo, do: Module.concat(["Logistics", "Repo"])
  def domain, do: Module.concat(["Logistics", "Freight"])
  def carrier, do: Module.concat(["Logistics", "Freight", "Carrier"])
  def warehouse, do: Module.concat(["Logistics", "Freight", "Warehouse"])
  def shipment, do: Module.concat(["Logistics", "Freight", "Shipment"])
  def parcel, do: Module.concat(["Logistics", "Freight", "Parcel"])
  def leg, do: Module.concat(["Logistics", "Freight", "ShipmentLeg"])

  def resources, do: [carrier(), warehouse(), shipment(), parcel(), leg()]

  def q(sql, params \\ []), do: repo().query!(sql, params).rows

  def create(resource, action, params) do
    resource
    |> Ash.Changeset.for_create(action, params)
    |> Ash.create()
  end

  def create!(resource, action, params) do
    {:ok, record} = create(resource, action, params)
    record
  end

  def truncate! do
    repo().query!(
      "TRUNCATE carriers, warehouses, shipments, parcels, shipment_legs RESTART IDENTITY CASCADE"
    )

    :ok
  end

  @doc "column_name => {sql_type, not_null?, default}"
  def columns(table) do
    """
    SELECT a.attname,
           format_type(a.atttypid, a.atttypmod),
           a.attnotnull,
           pg_get_expr(d.adbin, d.adrelid)
      FROM pg_attribute a
      LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
     WHERE a.attrelid = to_regclass('public.#{table}') AND a.attnum > 0 AND NOT a.attisdropped
    """
    |> q()
    |> Map.new(fn [name, type, notnull, default] -> {name, {type, notnull, default}} end)
  end

  def indexes do
    """
    SELECT i.relname,
           c.relname,
           ix.indisunique,
           ix.indisprimary,
           pg_get_indexdef(i.oid),
           pg_get_expr(ix.indpred, ix.indrelid)
      FROM pg_index ix
      JOIN pg_class i ON i.oid = ix.indexrelid
      JOIN pg_class c ON c.oid = ix.indrelid
      JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'public' AND c.relname <> 'schema_migrations'
    """
    |> q()
    |> Map.new(fn [index, table, uniq, primary, def_sql, pred] ->
      {index, %{table: table, unique: uniq, primary: primary, def: def_sql, predicate: pred}}
    end)
  end

  def constraints(type) do
    """
    SELECT con.conname,
           rel.relname,
           pg_get_constraintdef(con.oid),
           con.confdeltype,
           con.confupdtype
      FROM pg_constraint con
      JOIN pg_class rel ON rel.oid = con.conrelid
      JOIN pg_namespace n ON n.oid = rel.relnamespace
     WHERE n.nspname = 'public' AND con.contype = $1
    """
    |> q([type])
    |> Map.new(fn [name, table, definition, del, upd] ->
      {name, %{table: table, definition: definition, on_delete: del, on_update: upd}}
    end)
  end

  def norm(sql) when is_binary(sql) do
    sql |> String.replace(~r/\s+/, " ") |> String.trim()
  end
end

ExUnit.start(
  autorun: false,
  formatters: [Harbor.Formatter],
  seed: 0,
  colors: [enabled: false],
  timeout: 120_000,
  max_failures: :infinity
)

defmodule Harbor.Suite do
  use ExUnit.Case, async: false

  require Ash.Query

  alias Harbor.H

  @invalid Ash.Error.Invalid
  @invalid_attribute Ash.Error.Changes.InvalidAttribute

  setup do
    H.truncate!()
    :ok
  end

  # ------------------------------------------------------------------ schema --

  test "T01 the public schema contains exactly the five resource tables" do
    tables =
      H.q("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
      |> Enum.map(&hd/1)
      |> Enum.sort()

    assert tables == [
             "carriers",
             "parcels",
             "schema_migrations",
             "shipment_legs",
             "shipments",
             "warehouses"
           ]
  end

  test "T02 citext and uuid-ossp are installed and the ash support functions exist" do
    extensions = H.q("SELECT extname FROM pg_extension") |> Enum.map(&hd/1) |> Enum.sort()
    assert "citext" in extensions
    assert "uuid-ossp" in extensions

    functions =
      H.q("""
      SELECT DISTINCT p.proname
        FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
       WHERE n.nspname = 'public'
      """)
      |> Enum.map(&hd/1)
      |> Enum.sort()

    assert "ash_elixir_and" in functions
    assert "ash_elixir_or" in functions
    assert "ash_raise_error" in functions
  end

  test "T03 carriers has the required columns, sql types, nullability and defaults" do
    columns = H.columns("carriers")

    assert Map.keys(columns) |> Enum.sort() == ["code", "id", "name", "retired_at"]
    assert {"uuid", true, default} = columns["id"]
    assert is_binary(default) and default != ""
    assert {"citext", true, nil} == columns["code"]
    assert {"text", true, nil} == columns["name"]
    assert {"timestamp without time zone", false, nil} == columns["retired_at"]
  end

  test "T04 warehouses has the required columns, sql types, nullability and defaults" do
    columns = H.columns("warehouses")

    assert Map.keys(columns) |> Enum.sort() ==
             ["capacity_parcels", "code", "decommissioned", "id", "name", "region"]

    assert {"uuid", true, _} = columns["id"]
    assert {"text", true, nil} == columns["code"]
    assert {"text", true, nil} == columns["name"]
    assert {"text", true, nil} == columns["region"]
    assert {"bigint", true, "0"} == columns["capacity_parcels"]
    assert {"boolean", true, "false"} == columns["decommissioned"]
  end

  test "T05 shipments has the required columns, sql types, nullability and defaults" do
    columns = H.columns("shipments")

    assert Map.keys(columns) |> Enum.sort() ==
             [
               "booked_at",
               "carrier_id",
               "declared_value_cents",
               "id",
               "origin_warehouse_id",
               "reference",
               "scheduled_for",
               "status"
             ]

    assert {"uuid", true, _} = columns["id"]
    assert {"text", true, nil} == columns["reference"]
    assert {"text", true, "'draft'::text"} == columns["status"]
    assert {"bigint", true, "0"} == columns["declared_value_cents"]
    assert {"uuid", true, nil} == columns["carrier_id"]
    assert {"uuid", false, nil} == columns["origin_warehouse_id"]
  end

  test "T06 shipments.scheduled_for is stored as timestamp with time zone" do
    assert {"timestamp with time zone", false, nil} == H.columns("shipments")["scheduled_for"]
  end

  test "T07 shipments.booked_at is a nullable timestamp defaulting to now()" do
    assert {"timestamp without time zone", false, default} = H.columns("shipments")["booked_at"]
    assert is_binary(default)
    assert String.contains?(String.downcase(default), "now()")
  end

  test "T08 parcels and shipment_legs have the required columns, sql types and defaults" do
    parcels = H.columns("parcels")

    assert Map.keys(parcels) |> Enum.sort() ==
             ["fragile", "id", "shipment_id", "tracking_code", "weight_grams"]

    assert {"uuid", true, _} = parcels["id"]
    assert {"text", true, nil} == parcels["tracking_code"]
    assert {"bigint", true, nil} == parcels["weight_grams"]
    assert {"boolean", true, "false"} == parcels["fragile"]
    assert {"uuid", true, nil} == parcels["shipment_id"]

    legs = H.columns("shipment_legs")
    assert Map.keys(legs) |> Enum.sort() == ["id", "sequence", "shipment_id", "warehouse_id"]
    assert {"uuid", true, _} = legs["id"]
    assert {"bigint", true, nil} == legs["sequence"]
    assert {"uuid", true, nil} == legs["shipment_id"]
    assert {"uuid", true, nil} == legs["warehouse_id"]
  end

  test "T09 every table has a primary key named <table>_pkey over (id) only" do
    pkeys = H.constraints("p")

    for table <- ~w(carriers warehouses shipments parcels shipment_legs) do
      name = "#{table}_pkey"
      assert %{table: ^table, definition: definition} = pkeys[name]
      assert H.norm(definition) == "PRIMARY KEY (id)"
    end
  end

  test "T10 the shipments foreign keys use the required names and referential actions" do
    fks = H.constraints("f")

    carrier_fk = fks["shipments_carrier_fkey"]
    assert carrier_fk, "shipments_carrier_fkey is missing"
    assert carrier_fk.table == "shipments"
    assert H.norm(carrier_fk.definition) ==
             "FOREIGN KEY (carrier_id) REFERENCES carriers(id) ON UPDATE CASCADE ON DELETE RESTRICT"

    warehouse_fk = fks["shipments_origin_warehouse_fkey"]
    assert warehouse_fk, "shipments_origin_warehouse_fkey is missing"
    assert warehouse_fk.table == "shipments"
    assert H.norm(warehouse_fk.definition) ==
             "FOREIGN KEY (origin_warehouse_id) REFERENCES warehouses(id) ON UPDATE CASCADE ON DELETE SET NULL"
  end

  test "T11 the parcels and shipment_legs foreign keys use the required names and actions" do
    fks = H.constraints("f")

    parcel_fk = fks["parcels_shipment_fkey"]
    assert parcel_fk, "parcels_shipment_fkey is missing"
    assert parcel_fk.table == "parcels"
    assert H.norm(parcel_fk.definition) ==
             "FOREIGN KEY (shipment_id) REFERENCES shipments(id) ON UPDATE CASCADE ON DELETE CASCADE"

    leg_shipment_fk = fks["shipment_legs_shipment_fkey"]
    assert leg_shipment_fk, "shipment_legs_shipment_fkey is missing"
    assert H.norm(leg_shipment_fk.definition) ==
             "FOREIGN KEY (shipment_id) REFERENCES shipments(id) ON UPDATE CASCADE ON DELETE CASCADE"

    leg_warehouse_fk = fks["shipment_legs_warehouse_fkey"]
    assert leg_warehouse_fk, "shipment_legs_warehouse_fkey is missing"
    assert H.norm(leg_warehouse_fk.definition) ==
             "FOREIGN KEY (warehouse_id) REFERENCES warehouses(id) ON UPDATE CASCADE ON DELETE RESTRICT"
  end

  test "T12 the database contains exactly the five required foreign keys" do
    assert H.constraints("f") |> Map.keys() |> Enum.sort() == [
             "parcels_shipment_fkey",
             "shipment_legs_shipment_fkey",
             "shipment_legs_warehouse_fkey",
             "shipments_carrier_fkey",
             "shipments_origin_warehouse_fkey"
           ]
  end

  test "T13 plain btree indexes back every foreign key column" do
    indexes = H.indexes()

    for name <- [
          "shipments_carrier_id_index",
          "parcels_shipment_id_index",
          "shipment_legs_shipment_id_index",
          "shipment_legs_warehouse_id_index"
        ] do
      index = indexes[name]
      assert index, "index #{name} is missing"
      refute index.unique, "index #{name} must not be unique"
      assert index.predicate == nil, "index #{name} must not be partial"
    end
  end

  test "T14 carriers_unique_code_index is a partial unique index restricted to live carriers" do
    index = H.indexes()["carriers_unique_code_index"]
    assert index, "carriers_unique_code_index is missing"
    assert index.table == "carriers"
    assert index.unique
    assert H.norm(index.predicate || "") == "(retired_at IS NULL)"
    assert String.contains?(index.def, "(code)")
  end

  test "T15 warehouses_unique_active_code_index is partial on decommissioned = false" do
    index = H.indexes()["warehouses_unique_active_code_index"]
    assert index, "warehouses_unique_active_code_index is missing"
    assert index.table == "warehouses"
    assert index.unique
    assert H.norm(index.predicate || "") == "(decommissioned = false)"
    assert String.contains?(index.def, "(code)")
  end

  test "T16 parcels_single_fragile_per_shipment_index is partial on fragile = true" do
    index = H.indexes()["parcels_single_fragile_per_shipment_index"]
    assert index, "parcels_single_fragile_per_shipment_index is missing"
    assert index.table == "parcels"
    assert index.unique
    assert H.norm(index.predicate || "") == "(fragile = true)"
    assert String.contains?(index.def, "(shipment_id)")
  end

  test "T17 the remaining identity indexes are unique and unconditional" do
    indexes = H.indexes()

    expected = %{
      "shipments_unique_reference_index" => {"shipments", "(reference)"},
      "parcels_unique_tracking_code_index" => {"parcels", "(tracking_code)"},
      "shipment_legs_unique_leg_sequence_index" => {"shipment_legs", "(shipment_id, sequence)"}
    }

    for {name, {table, columns}} <- expected do
      index = indexes[name]
      assert index, "index #{name} is missing"
      assert index.table == table
      assert index.unique
      assert index.predicate == nil, "index #{name} must not be partial"
      assert String.contains?(index.def, columns)
    end
  end

  test "T18 no unexpected indexes exist in the public schema" do
    assert H.indexes() |> Map.keys() |> Enum.sort() == [
             "carriers_pkey",
             "carriers_unique_code_index",
             "parcels_pkey",
             "parcels_shipment_id_index",
             "parcels_single_fragile_per_shipment_index",
             "parcels_unique_tracking_code_index",
             "shipment_legs_pkey",
             "shipment_legs_shipment_id_index",
             "shipment_legs_unique_leg_sequence_index",
             "shipment_legs_warehouse_id_index",
             "shipments_carrier_id_index",
             "shipments_pkey",
             "shipments_unique_reference_index",
             "warehouses_pkey",
             "warehouses_unique_active_code_index"
           ]
  end

  test "T19 exactly the four required check constraints exist" do
    checks = H.constraints("c")

    assert Map.keys(checks) |> Enum.sort() == [
             "parcels_weight_grams_positive",
             "shipment_legs_sequence_positive",
             "shipments_declared_value_cents_non_negative",
             "warehouses_capacity_parcels_non_negative"
           ]

    assert checks["warehouses_capacity_parcels_non_negative"].table == "warehouses"

    assert H.norm(checks["warehouses_capacity_parcels_non_negative"].definition) ==
             "CHECK ((capacity_parcels >= 0))"

    assert checks["shipments_declared_value_cents_non_negative"].table == "shipments"

    assert H.norm(checks["shipments_declared_value_cents_non_negative"].definition) ==
             "CHECK ((declared_value_cents >= 0))"

    assert checks["parcels_weight_grams_positive"].table == "parcels"
    assert H.norm(checks["parcels_weight_grams_positive"].definition) == "CHECK ((weight_grams > 0))"

    assert checks["shipment_legs_sequence_positive"].table == "shipment_legs"

    assert H.norm(checks["shipment_legs_sequence_positive"].definition) ==
             "CHECK ((sequence >= 1))"
  end

  test "T20 the migrations and resource snapshots were produced by the ash_postgres generator" do
    migrations =
      "priv/repo/migrations"
      |> File.ls!()
      |> Enum.filter(&String.ends_with?(&1, ".exs"))

    assert length(migrations) >= 2,
           "expected at least two generated migration files, found #{inspect(migrations)}"

    bodies = Enum.map(migrations, &File.read!(Path.join("priv/repo/migrations", &1)))

    assert Enum.any?(
             bodies,
             &String.contains?(&1, "autogenerated with `mix ash_postgres.generate_migrations`")
           ),
           "no migration carries the ash_postgres migration generator header"

    snapshot_root = "priv/resource_snapshots/repo"
    assert File.dir?(snapshot_root), "#{snapshot_root} is missing"

    for table <- ~w(carriers warehouses shipments parcels shipment_legs) do
      dir = Path.join(snapshot_root, table)
      assert File.dir?(dir), "resource snapshot directory #{dir} is missing"

      assert Enum.any?(File.ls!(dir), &String.ends_with?(&1, ".json")),
             "no snapshot json in #{dir}"
    end

    extensions =
      snapshot_root |> Path.join("extensions.json") |> File.read!() |> Jason.decode!()

    assert extensions["installed"] == ["ash-functions", "citext", "uuid-ossp"]
  end

  test "T21 the repo is an ash_postgres repo with the required version and extensions" do
    assert H.repo().__adapter__() == Ecto.Adapters.Postgres
    assert H.repo().min_pg_version() == %Version{major: 16, minor: 0, patch: 0}
    assert H.repo().installed_extensions() == ["ash-functions", "citext", "uuid-ossp"]
  end

  test "T22 every resource is stored in postgres through Logistics.Repo" do
    assert Ash.Domain.Info.resources(H.domain()) |> Enum.sort() == Enum.sort(H.resources())

    tables = %{
      H.carrier() => "carriers",
      H.warehouse() => "warehouses",
      H.shipment() => "shipments",
      H.parcel() => "parcels",
      H.leg() => "shipment_legs"
    }

    for {resource, table} <- tables do
      assert Ash.DataLayer.data_layer(resource) == AshPostgres.DataLayer
      assert AshPostgres.DataLayer.Info.table(resource) == table
      assert AshPostgres.DataLayer.Info.repo(resource, :mutate) == H.repo()
    end
  end

  # --------------------------------------------------------------- behaviour --

  test "T23 carrier codes are unique case-insensitively" do
    H.create!(H.carrier(), :create, %{code: "acme", name: "Acme Freight"})

    assert {:error, %@invalid{errors: [%@invalid_attribute{field: :code, message: message}]}} =
             H.create(H.carrier(), :create, %{code: "ACME", name: "Acme Two"})

    assert message == "has already been taken"
    assert H.q("SELECT count(*) FROM carriers") == [[1]]
  end

  test "T24 carrier codes compare case-insensitively when reading" do
    H.create!(H.carrier(), :create, %{code: "acme", name: "Acme Freight"})

    found =
      H.carrier()
      |> Ash.Query.filter(code == "ACME")
      |> Ash.read!()

    assert length(found) == 1
    assert to_string(hd(found).code) == "acme"
  end

  test "T25 retired carriers disappear from reads but stay in the table and free their code" do
    carrier = H.create!(H.carrier(), :create, %{code: "acme", name: "Acme Freight"})

    {:ok, _} =
      carrier
      |> Ash.Changeset.for_update(:update, %{retired_at: ~U[2026-01-01 00:00:00.000000Z]})
      |> Ash.update()

    assert Ash.read!(H.carrier()) == []
    assert H.q("SELECT count(*) FROM carriers") == [[1]]

    replacement = H.create!(H.carrier(), :create, %{code: "acme", name: "Acme Reborn"})
    assert replacement.name == "Acme Reborn"
    assert H.q("SELECT count(*) FROM carriers") == [[2]]
    assert Ash.read!(H.carrier()) |> length() == 1
  end

  test "T26 warehouse codes are unique among active warehouses only" do
    warehouse =
      H.create!(H.warehouse(), :create, %{
        code: "WH-1",
        name: "West Hub",
        region: "west",
        capacity_parcels: 40
      })

    assert {:error, %@invalid{errors: [%@invalid_attribute{field: :code, message: message}]}} =
             H.create(H.warehouse(), :create, %{code: "WH-1", name: "Clash", region: "west"})

    assert message == "has already been taken"

    {:ok, _} =
      warehouse
      |> Ash.Changeset.for_update(:update, %{decommissioned: true})
      |> Ash.update()

    assert %{code: "WH-1"} =
             H.create!(H.warehouse(), :create, %{
               code: "WH-1",
               name: "West Hub II",
               region: "west"
             })
  end

  test "T27 negative warehouse capacity is rejected by the database check constraint" do
    assert {:error,
            %@invalid{
              errors: [%@invalid_attribute{field: :capacity_parcels, message: message}]
            }} =
             H.create(H.warehouse(), :create, %{
               code: "WH-9",
               name: "Bad",
               region: "north",
               capacity_parcels: -1
             })

    assert message == "capacity must not be negative"
    assert H.q("SELECT count(*) FROM warehouses") == [[0]]
  end

  test "T28 a negative declared value is rejected by the database check constraint" do
    carrier = H.create!(H.carrier(), :create, %{code: "acme", name: "Acme"})

    assert {:error,
            %@invalid{
              errors: [%@invalid_attribute{field: :declared_value_cents, message: message}]
            }} =
             H.create(H.shipment(), :create, %{
               reference: "S-NEG",
               carrier_id: carrier.id,
               declared_value_cents: -1
             })

    assert message == "declared value must not be negative"
    assert H.q("SELECT count(*) FROM shipments") == [[0]]
  end

  test "T29 a non-positive parcel weight is rejected by the database check constraint" do
    shipment = fixture_shipment("S-1")

    assert {:error,
            %@invalid{errors: [%@invalid_attribute{field: :weight_grams, message: message}]}} =
             H.create(H.parcel(), :create, %{
               tracking_code: "P-0",
               weight_grams: 0,
               shipment_id: shipment.id
             })

    assert message == "weight must be positive"
    assert H.q("SELECT count(*) FROM parcels") == [[0]]
  end

  test "T30 a zero leg sequence is rejected by the database check constraint" do
    shipment = fixture_shipment("S-1")
    warehouse = fixture_warehouse("WH-1")

    assert {:error, %@invalid{errors: [%@invalid_attribute{field: :sequence, message: message}]}} =
             H.create(H.leg(), :create, %{
               shipment_id: shipment.id,
               warehouse_id: warehouse.id,
               sequence: 0
             })

    assert message == "sequence must be at least 1"
    assert H.q("SELECT count(*) FROM shipment_legs") == [[0]]
  end

  test "T31 shipment references are unique" do
    carrier = H.create!(H.carrier(), :create, %{code: "acme", name: "Acme"})
    H.create!(H.shipment(), :create, %{reference: "S-1", carrier_id: carrier.id})

    assert {:error, %@invalid{errors: [%@invalid_attribute{field: :reference, message: message}]}} =
             H.create(H.shipment(), :create, %{reference: "S-1", carrier_id: carrier.id})

    assert message == "has already been taken"
    assert H.q("SELECT count(*) FROM shipments") == [[1]]
  end

  test "T32 parcel tracking codes are unique across shipments" do
    first = fixture_shipment("S-1")
    second = fixture_shipment("S-2")

    H.create!(H.parcel(), :create, %{
      tracking_code: "TRK-1",
      weight_grams: 100,
      shipment_id: first.id
    })

    assert {:error,
            %@invalid{errors: [%@invalid_attribute{field: :tracking_code, message: message}]}} =
             H.create(H.parcel(), :create, %{
               tracking_code: "TRK-1",
               weight_grams: 100,
               shipment_id: second.id
             })

    assert message == "has already been taken"
    assert H.q("SELECT count(*) FROM parcels") == [[1]]
  end

  test "T33 at most one fragile parcel is allowed per shipment" do
    shipment = fixture_shipment("S-1")

    H.create!(H.parcel(), :create, %{
      tracking_code: "TRK-1",
      weight_grams: 100,
      fragile: true,
      shipment_id: shipment.id
    })

    assert {:error,
            %@invalid{errors: [%@invalid_attribute{field: :shipment_id, message: message}]}} =
             H.create(H.parcel(), :create, %{
               tracking_code: "TRK-2",
               weight_grams: 100,
               fragile: true,
               shipment_id: shipment.id
             })

    assert message == "has already been taken"

    assert %{fragile: false} =
             H.create!(H.parcel(), :create, %{
               tracking_code: "TRK-3",
               weight_grams: 100,
               fragile: false,
               shipment_id: shipment.id
             })

    assert H.q("SELECT count(*) FROM parcels") == [[2]]
  end

  test "T34 a shipment cannot have two legs with the same sequence" do
    shipment = fixture_shipment("S-1")
    warehouse = fixture_warehouse("WH-1")

    H.create!(H.leg(), :create, %{
      shipment_id: shipment.id,
      warehouse_id: warehouse.id,
      sequence: 1
    })

    assert {:error,
            %@invalid{errors: [%@invalid_attribute{field: :shipment_id, message: message}]}} =
             H.create(H.leg(), :create, %{
               shipment_id: shipment.id,
               warehouse_id: warehouse.id,
               sequence: 1
             })

    assert message == "has already been taken"

    assert %{sequence: 2} =
             H.create!(H.leg(), :create, %{
               shipment_id: shipment.id,
               warehouse_id: warehouse.id,
               sequence: 2
             })
  end

  test "T35 a carrier that still has shipments cannot be destroyed" do
    carrier = H.create!(H.carrier(), :create, %{code: "acme", name: "Acme"})
    H.create!(H.shipment(), :create, %{reference: "S-1", carrier_id: carrier.id})

    assert {:error, %@invalid{errors: [%@invalid_attribute{field: :shipments, message: message}]}} =
             Ash.destroy(carrier)

    assert message == "carrier still has shipments"
    assert H.q("SELECT count(*) FROM carriers") == [[1]]
  end

  test "T36 a warehouse that still has shipment legs cannot be destroyed" do
    shipment = fixture_shipment("S-1")
    warehouse = fixture_warehouse("WH-1")

    H.create!(H.leg(), :create, %{
      shipment_id: shipment.id,
      warehouse_id: warehouse.id,
      sequence: 1
    })

    assert {:error, %@invalid{errors: [%@invalid_attribute{field: :legs, message: message}]}} =
             Ash.destroy(warehouse)

    assert message == "warehouse still has shipment legs"
    assert H.q("SELECT count(*) FROM warehouses") == [[1]]
  end

  test "T37 destroying a shipment cascades to its parcels and legs" do
    shipment = fixture_shipment("S-1")
    warehouse = fixture_warehouse("WH-1")

    H.create!(H.parcel(), :create, %{
      tracking_code: "TRK-1",
      weight_grams: 100,
      shipment_id: shipment.id
    })

    H.create!(H.leg(), :create, %{
      shipment_id: shipment.id,
      warehouse_id: warehouse.id,
      sequence: 1
    })

    assert :ok = Ash.destroy(shipment)

    assert H.q("SELECT count(*) FROM shipments") == [[0]]
    assert H.q("SELECT count(*) FROM parcels") == [[0]]
    assert H.q("SELECT count(*) FROM shipment_legs") == [[0]]
  end

  test "T38 destroying an origin warehouse nils the reference on its shipments" do
    carrier = H.create!(H.carrier(), :create, %{code: "acme", name: "Acme"})
    warehouse = fixture_warehouse("WH-1")

    H.create!(H.shipment(), :create, %{
      reference: "S-1",
      carrier_id: carrier.id,
      origin_warehouse_id: warehouse.id
    })

    assert :ok = Ash.destroy(warehouse)

    assert H.q("SELECT origin_warehouse_id FROM shipments WHERE reference = 'S-1'") == [[nil]]
    assert H.q("SELECT count(*) FROM warehouses") == [[0]]
  end

  # ---------------------------------------------- transactions & push-down ----

  test "T39 a rejected parcel rolls the whole intake back" do
    carrier = H.create!(H.carrier(), :create, %{code: "acme", name: "Acme"})

    assert {:error, %@invalid{}} =
             H.create(H.shipment(), :intake, %{
               reference: "S-BAD",
               carrier_id: carrier.id,
               parcels: [
                 %{tracking_code: "TB1", weight_grams: 10},
                 %{tracking_code: "TB2", weight_grams: -1}
               ]
             })

    assert H.q("SELECT count(*) FROM shipments WHERE reference = 'S-BAD'") == [[0]]
    assert H.q("SELECT count(*) FROM parcels WHERE tracking_code IN ('TB1', 'TB2')") == [[0]]
  end

  test "T40 a successful intake commits the shipment together with its parcels" do
    carrier = H.create!(H.carrier(), :create, %{code: "acme", name: "Acme"})

    shipment =
      H.create!(H.shipment(), :intake, %{
        reference: "S-GOOD",
        carrier_id: carrier.id,
        declared_value_cents: 12_500,
        parcels: [
          %{tracking_code: "TG1", weight_grams: 4000},
          %{tracking_code: "TG2", weight_grams: 3000}
        ]
      })

    assert H.q("SELECT count(*) FROM shipments WHERE reference = 'S-GOOD'") == [[1]]

    assert H.q("SELECT count(*) FROM parcels WHERE shipment_id = $1", [
             Ecto.UUID.dump!(shipment.id)
           ]) == [[2]]

    reloaded =
      H.shipment()
      |> Ash.Query.filter(reference == "S-GOOD")
      |> Ash.Query.load([:parcels])
      |> Ash.read_one!()

    assert reloaded.declared_value_cents == 12_500
    assert length(reloaded.parcels) == 2
  end

  test "T41 the parcel_count and total_weight_grams aggregates are filterable" do
    carrier = H.create!(H.carrier(), :create, %{code: "acme", name: "Acme"})

    H.create!(H.shipment(), :intake, %{
      reference: "S-GOOD",
      carrier_id: carrier.id,
      parcels: [
        %{tracking_code: "TG1", weight_grams: 4000},
        %{tracking_code: "TG2", weight_grams: 3000}
      ]
    })

    H.create!(H.shipment(), :intake, %{
      reference: "S-SMALL",
      carrier_id: carrier.id,
      parcels: [%{tracking_code: "TS1", weight_grams: 1000}]
    })

    results =
      H.shipment()
      |> Ash.Query.filter(parcel_count >= 2)
      |> Ash.Query.load([:parcel_count, :total_weight_grams])
      |> Ash.read!()

    assert Enum.map(results, & &1.reference) == ["S-GOOD"]
    assert hd(results).parcel_count == 2
    assert hd(results).total_weight_grams == 7000
  end

  test "T42 the heavy? calculation is filterable" do
    carrier = H.create!(H.carrier(), :create, %{code: "acme", name: "Acme"})

    H.create!(H.shipment(), :intake, %{
      reference: "S-GOOD",
      carrier_id: carrier.id,
      parcels: [
        %{tracking_code: "TG1", weight_grams: 4000},
        %{tracking_code: "TG2", weight_grams: 3000}
      ]
    })

    H.create!(H.shipment(), :intake, %{
      reference: "S-SMALL",
      carrier_id: carrier.id,
      parcels: [%{tracking_code: "TS1", weight_grams: 1000}]
    })

    heavy =
      H.shipment()
      |> Ash.Query.filter(heavy? == true)
      |> Ash.read!()
      |> Enum.map(& &1.reference)

    assert heavy == ["S-GOOD"]

    loaded =
      H.shipment()
      |> Ash.Query.filter(reference == "S-SMALL")
      |> Ash.Query.load([:heavy?])
      |> Ash.read_one!()

    assert loaded.heavy? == false
  end

  test "T43 an aggregate-filtered read reaches the database exactly once" do
    carrier = H.create!(H.carrier(), :create, %{code: "acme", name: "Acme"})

    H.create!(H.shipment(), :intake, %{
      reference: "S-GOOD",
      carrier_id: carrier.id,
      parcels: [
        %{tracking_code: "TG1", weight_grams: 4000},
        %{tracking_code: "TG2", weight_grams: 3000}
      ]
    })

    handler_id = "harbor-query-counter"
    parent = self()

    :telemetry.attach_many(
      handler_id,
      [[:logistics, :repo, :query]],
      fn _event, _measurements, _metadata, _config -> send(parent, :repo_query) end,
      nil
    )

    try do
      H.shipment()
      |> Ash.Query.filter(parcel_count >= 2)
      |> Ash.Query.load([:parcel_count])
      |> Ash.read!()
    after
      :telemetry.detach(handler_id)
    end

    assert drain_queries(0) == 1
  end

  test "T44 booked_at falls back to the database default and scheduled_for round-trips" do
    carrier = H.create!(H.carrier(), :create, %{code: "acme", name: "Acme"})

    shipment =
      H.create!(H.shipment(), :create, %{
        reference: "S-1",
        carrier_id: carrier.id,
        scheduled_for: ~U[2027-03-04 05:06:07Z]
      })

    assert shipment.booked_at != nil
    assert shipment.scheduled_for == ~U[2027-03-04 05:06:07Z]

    reloaded = H.shipment() |> Ash.Query.filter(reference == "S-1") |> Ash.read_one!()
    assert reloaded.scheduled_for == ~U[2027-03-04 05:06:07Z]
    assert reloaded.booked_at != nil
  end

  test "T45 a rolled back repo transaction writes nothing" do
    result =
      H.repo().transaction(fn ->
        H.create!(H.carrier(), :create, %{code: "tx-only", name: "Rollback"})
        H.repo().rollback(:discarded)
      end)

    assert result == {:error, :discarded}
    assert H.q("SELECT count(*) FROM carriers WHERE code = 'tx-only'") == [[0]]
  end

  # ----------------------------------------------------------------- helpers --

  defp fixture_warehouse(code) do
    H.create!(H.warehouse(), :create, %{
      code: code,
      name: "Hub #{code}",
      region: "west",
      capacity_parcels: 25
    })
  end

  defp fixture_shipment(reference) do
    carrier =
      case Ash.read!(H.carrier()) do
        [carrier | _] -> carrier
        [] -> H.create!(H.carrier(), :create, %{code: "acme", name: "Acme"})
      end

    H.create!(H.shipment(), :create, %{reference: reference, carrier_id: carrier.id})
  end

  defp drain_queries(count) do
    receive do
      :repo_query -> drain_queries(count + 1)
    after
      0 -> count
    end
  end
end

ExUnit.run()
'''


def _env():
    env = os.environ.copy()
    env["MIX_ENV"] = "dev"
    env.setdefault("HEX_OFFLINE", "1")
    return env


def _run(args, timeout=1200):
    return subprocess.run(
        args,
        cwd=PROJECT_DIR,
        capture_output=True,
        text=True,
        timeout=timeout,
        stdin=subprocess.DEVNULL,
        env=_env(),
    )


def _tail(text, limit=4000):
    text = text or ""
    return text[-limit:]


@pytest.fixture(scope="session")
def harness():
    pg = subprocess.run(
        ["pg-start"], capture_output=True, text=True, timeout=300, stdin=subprocess.DEVNULL
    )

    compile_proc = _run(["mix", "compile"])

    codegen_proc = None
    reset_proc = None
    run_proc = None

    if compile_proc.returncode == 0:
        codegen_proc = _run(["mix", "ash.codegen", "--check"])
        reset_proc = _run(["mix", "ash.reset"])

        if reset_proc.returncode == 0:
            with open(HARNESS_PATH, "w", encoding="utf-8") as handle:
                handle.write(HARNESS_EXS)
            run_proc = _run(["mix", "run", HARNESS_PATH])

    results = {}
    if run_proc is not None:
        for line in run_proc.stdout.splitlines():
            if not line.startswith(MARKER):
                continue
            parts = line.split("@@")
            # ["", "HARBOR", name, status, encoded_detail]
            if len(parts) < 5:
                continue
            name = parts[2]
            status = parts[3]
            try:
                detail = base64.b64decode(parts[4]).decode("utf-8", "replace")
            except Exception:  # noqa: BLE001 - malformed detail must not hide the result
                detail = parts[4]
            results[name] = (status, detail)

    return {
        "pg": pg,
        "compile": compile_proc,
        "codegen": codegen_proc,
        "reset": reset_proc,
        "run": run_proc,
        "results": results,
    }


def _diagnostics(harness):
    lines = []
    for label in ("pg", "compile", "codegen", "reset", "run"):
        proc = harness.get(label)
        if proc is None:
            lines.append(f"[{label}] not executed")
            continue
        lines.append(
            f"[{label}] exit={proc.returncode}\n"
            f"stdout tail:\n{_tail(proc.stdout)}\n"
            f"stderr tail:\n{_tail(proc.stderr)}"
        )
    return "\n\n".join(lines)


def _scenario(harness, scenario_id):
    prefix = f"test {scenario_id} "
    matches = [name for name in harness["results"] if name.startswith(prefix)]
    assert matches, (
        f"Scenario {scenario_id} produced no result. The ExUnit suite did not run "
        f"or crashed before reaching it.\n\n{_diagnostics(harness)}"
    )
    name = matches[0]
    status, detail = harness["results"][name]
    assert status == "pass", f"Scenario {scenario_id} failed: {name}\n{detail}"


# --------------------------------------------------------------------- gates --


def test_project_compiles(harness):
    proc = harness["compile"]
    assert proc.returncode == 0, (
        "`mix compile` failed in /home/user/logistics.\n"
        f"stdout tail:\n{_tail(proc.stdout)}\nstderr tail:\n{_tail(proc.stderr)}"
    )


def test_codegen_reports_no_pending_changes(harness):
    proc = harness["codegen"]
    assert proc is not None, f"`mix ash.codegen --check` was not run.\n\n{_diagnostics(harness)}"
    assert proc.returncode == 0, (
        "`mix ash.codegen --check` exited non-zero, so the committed migrations and "
        "resource snapshots do not match the resources (a second codegen run would "
        "produce new files).\n"
        f"stdout tail:\n{_tail(proc.stdout)}\nstderr tail:\n{_tail(proc.stderr)}"
    )


def test_ash_reset_rebuilds_the_database(harness):
    proc = harness["reset"]
    assert proc is not None, f"`mix ash.reset` was not run.\n\n{_diagnostics(harness)}"
    assert proc.returncode == 0, (
        "`mix ash.reset` failed, so the database cannot be rebuilt from the generated "
        "migrations.\n"
        f"stdout tail:\n{_tail(proc.stdout)}\nstderr tail:\n{_tail(proc.stderr)}"
    )


def test_probe_suite_executed(harness):
    proc = harness["run"]
    assert proc is not None, f"The ExUnit probe suite was never started.\n\n{_diagnostics(harness)}"
    assert harness["results"], (
        "The ExUnit probe suite produced no scenario results.\n\n" + _diagnostics(harness)
    )


# ------------------------------------------------------------------ scenarios --


def test_t01_public_schema_contains_exactly_the_five_tables(harness):
    _scenario(harness, "T01")


def test_t02_citext_uuid_ossp_and_ash_functions_installed(harness):
    _scenario(harness, "T02")


def test_t03_carriers_columns(harness):
    _scenario(harness, "T03")


def test_t04_warehouses_columns(harness):
    _scenario(harness, "T04")


def test_t05_shipments_columns(harness):
    _scenario(harness, "T05")


def test_t06_scheduled_for_is_timestamptz(harness):
    _scenario(harness, "T06")


def test_t07_booked_at_defaults_to_now(harness):
    _scenario(harness, "T07")


def test_t08_parcels_and_shipment_legs_columns(harness):
    _scenario(harness, "T08")


def test_t09_primary_keys(harness):
    _scenario(harness, "T09")


def test_t10_shipments_foreign_keys(harness):
    _scenario(harness, "T10")


def test_t11_parcels_and_leg_foreign_keys(harness):
    _scenario(harness, "T11")


def test_t12_exactly_five_foreign_keys(harness):
    _scenario(harness, "T12")


def test_t13_foreign_key_backing_indexes(harness):
    _scenario(harness, "T13")


def test_t14_carriers_partial_unique_index(harness):
    _scenario(harness, "T14")


def test_t15_warehouses_partial_unique_index(harness):
    _scenario(harness, "T15")


def test_t16_single_fragile_parcel_partial_index(harness):
    _scenario(harness, "T16")


def test_t17_remaining_unique_indexes(harness):
    _scenario(harness, "T17")


def test_t18_no_unexpected_indexes(harness):
    _scenario(harness, "T18")


def test_t19_check_constraints(harness):
    _scenario(harness, "T19")


def test_t20_generated_migrations_and_snapshots(harness):
    _scenario(harness, "T20")


def test_t21_repo_contract(harness):
    _scenario(harness, "T21")


def test_t22_resources_wired_to_postgres(harness):
    _scenario(harness, "T22")


def test_t23_carrier_code_unique_case_insensitively(harness):
    _scenario(harness, "T23")


def test_t24_carrier_code_reads_case_insensitively(harness):
    _scenario(harness, "T24")


def test_t25_retired_carriers_are_hidden_and_free_their_code(harness):
    _scenario(harness, "T25")


def test_t26_warehouse_codes_unique_among_active(harness):
    _scenario(harness, "T26")


def test_t27_warehouse_capacity_check_constraint(harness):
    _scenario(harness, "T27")


def test_t28_shipment_declared_value_check_constraint(harness):
    _scenario(harness, "T28")


def test_t29_parcel_weight_check_constraint(harness):
    _scenario(harness, "T29")


def test_t30_leg_sequence_check_constraint(harness):
    _scenario(harness, "T30")


def test_t31_shipment_reference_unique(harness):
    _scenario(harness, "T31")


def test_t32_parcel_tracking_code_unique(harness):
    _scenario(harness, "T32")


def test_t33_single_fragile_parcel_per_shipment(harness):
    _scenario(harness, "T33")


def test_t34_leg_sequence_unique_per_shipment(harness):
    _scenario(harness, "T34")


def test_t35_carrier_destroy_restricted(harness):
    _scenario(harness, "T35")


def test_t36_warehouse_destroy_restricted(harness):
    _scenario(harness, "T36")


def test_t37_shipment_destroy_cascades(harness):
    _scenario(harness, "T37")


def test_t38_origin_warehouse_destroy_nilifies(harness):
    _scenario(harness, "T38")


def test_t39_intake_rolls_back_on_rejected_parcel(harness):
    _scenario(harness, "T39")


def test_t40_intake_commits_shipment_with_parcels(harness):
    _scenario(harness, "T40")


def test_t41_aggregates_are_filterable(harness):
    _scenario(harness, "T41")


def test_t42_heavy_calculation_is_filterable(harness):
    _scenario(harness, "T42")


def test_t43_aggregate_read_hits_the_database_once(harness):
    _scenario(harness, "T43")


def test_t44_booked_at_default_and_scheduled_for_roundtrip(harness):
    _scenario(harness, "T44")


def test_t45_repo_transaction_rollback_writes_nothing(harness):
    _scenario(harness, "T45")
