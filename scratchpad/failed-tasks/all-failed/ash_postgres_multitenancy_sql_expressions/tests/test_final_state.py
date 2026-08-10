"""Final-state verification for ash_postgres_multitenancy_sql_expressions.

The whole contract is exercised by a self-contained ExUnit suite that is written to
/tmp at verification time and executed with `mix run` inside the executor's project.
Each ExUnit scenario reports one machine readable line, and this module maps one
pytest function per scenario so failures are reported granularly.
"""

import base64
import os
import re
import subprocess

import pytest

PROJECT_DIR = "/home/user/billing"
SUITE_PATH = "/tmp/harbor_pgtenant_suite.exs"
RESULT_RE = re.compile(r"^@@HARBOR@@(?P<name>.*?)@@(?P<status>pass|fail|skip)@@(?P<detail>.*)$")

SUITE_EXS = r'''
defmodule Harbor.Formatter do
  @moduledoc false
  use GenServer

  def init(_opts), do: {:ok, %{}}

  def handle_cast({:test_finished, %ExUnit.Test{} = test}, state) do
    {status, detail} =
      case test.state do
        nil ->
          {"pass", ""}

        {:excluded, reason} ->
          {"skip", to_string(reason)}

        {:skipped, reason} ->
          {"skip", to_string(reason)}

        {:failed, failures} ->
          {"fail",
           ExUnit.Formatter.format_test_failure(test, failures, 1, 120, fn _, msg -> msg end)}

        {:invalid, _module} ->
          {"fail", "setup_all failed"}
      end

    IO.puts(
      "@@HARBOR@@" <>
        to_string(test.name) <> "@@" <> status <> "@@" <> Base.encode64(detail || "")
    )

    {:noreply, state}
  end

  def handle_cast(_event, state), do: {:noreply, state}
end

ExUnit.start(
  autorun: false,
  formatters: [Harbor.Formatter],
  seed: 0,
  colors: [enabled: false],
  timeout: 180_000,
  max_failures: :infinity
)

defmodule Harbor.Sql do
  @moduledoc false

  @noise ["begin", "commit", "rollback"]

  def capture(fun) do
    {:ok, agent} = Agent.start_link(fn -> [] end)
    id = "harbor-sql-#{System.unique_integer([:positive])}"

    :telemetry.attach(
      id,
      [:billing, :repo, :query],
      fn _event, _measure, meta, _cfg ->
        Agent.update(agent, fn acc -> [Map.get(meta, :query, "") | acc] end)
      end,
      nil
    )

    result =
      try do
        fun.()
      after
        :telemetry.detach(id)
      end

    queries = Agent.get(agent, &Enum.reverse/1)
    Agent.stop(agent)
    {result, Enum.reject(queries, &noise?/1)}
  end

  defp noise?(query) do
    q = query |> to_string() |> String.trim() |> String.downcase()

    q in @noise or String.starts_with?(q, "savepoint") or
      String.starts_with?(q, "release savepoint") or String.starts_with?(q, "rollback to")
  end

  def joined(queries), do: Enum.join(queries, "\n")
end

defmodule Harbor.FinalTest do
  use ExUnit.Case, async: false

  require Ash.Query

  @domain Module.concat(["Billing", "Metering"])
  @tenancy Module.concat(["Billing", "Tenancy"])
  @organisation Module.concat(["Billing", "Metering", "Organisation"])
  @plan_rate Module.concat(["Billing", "Metering", "PlanRate"])
  @subscription Module.concat(["Billing", "Metering", "Subscription"])
  @usage_record Module.concat(["Billing", "Metering", "UsageRecord"])
  @invoice Module.concat(["Billing", "Metering", "Invoice"])
  @invoice_line Module.concat(["Billing", "Metering", "InvoiceLine"])
  @tag_res Module.concat(["Billing", "Metering", "Tag"])
  @invoice_tag Module.concat(["Billing", "Metering", "InvoiceTag"])
  @repo Module.concat(["Billing", "Repo"])
  @trace Module.concat(["Billing", "Trace"])

  @acme "tenant_acme"
  @globex "tenant_globex"
  @initech "tenant_initech"

  defp d(fun, args), do: apply(@domain, fun, args)

  defp rows(sql, params \\ []) do
    apply(@repo, :query!, [sql, params]).rows
  end

  defp sub_by(code, tenant) do
    @subscription
    |> Ash.Query.filter(code == ^code)
    |> Ash.read_one!(tenant: tenant)
  end

  defp invoice_by(number, tenant) do
    @invoice
    |> Ash.Query.filter(number == ^number)
    |> Ash.read_one!(tenant: tenant)
  end

  setup_all do
    d(:register_organisation!, ["acme", "Acme Ltd", "pro"])
    d(:register_organisation!, ["globex", "Globex Inc", "free"])
    d(:register_organisation!, ["initech", "Initech Co", "free"])

    pro = d(:define_plan_rate!, ["pro", 25, 100])
    free = d(:define_plan_rate!, ["free", 40, 10])

    s1 =
      d(:open_subscription!, [
        %{
          code: "SUB-001",
          plan_code: "pro",
          monthly_cents: 5000,
          balance_cents: 1000,
          started_on: ~D[2026-01-01],
          plan_rate_id: pro.id
        },
        [tenant: @acme]
      ])

    s2 =
      d(:open_subscription!, [
        %{
          code: "SUB-002",
          plan_code: "pro",
          monthly_cents: 7000,
          balance_cents: 0,
          started_on: ~D[2026-02-01],
          plan_rate_id: pro.id
        },
        [tenant: @acme]
      ])

    _s3 =
      d(:open_subscription!, [
        %{
          code: "ZED-777",
          plan_code: "free",
          monthly_cents: 900,
          balance_cents: 0,
          started_on: ~D[2026-03-01],
          plan_rate_id: free.id
        },
        [tenant: @acme]
      ])

    g1 =
      d(:open_subscription!, [
        %{
          code: "SUB-001",
          plan_code: "free",
          monthly_cents: 300,
          balance_cents: 5000,
          started_on: ~D[2026-01-15],
          plan_rate_id: free.id
        },
        [tenant: @globex]
      ])

    for {metric, qty, price, at} <- [
          {"api_calls", 120, 3, ~U[2026-03-01 10:00:00Z]},
          {"storage", 40, 7, ~U[2026-03-05 10:00:00Z]},
          {"api_calls", 30, 3, ~U[2026-04-09 10:00:00Z]}
        ] do
      d(:record_usage!, [
        %{
          metric: metric,
          quantity: qty,
          unit_price_cents: price,
          recorded_at: at,
          subscription_id: s1.id
        },
        [tenant: @acme]
      ])
    end

    d(:record_usage!, [
      %{
        metric: "storage",
        quantity: 10,
        unit_price_cents: 5,
        recorded_at: ~U[2026-03-02 10:00:00Z],
        subscription_id: s2.id
      },
      [tenant: @acme]
    ])

    d(:record_usage!, [
      %{
        metric: "api_calls",
        quantity: 30,
        unit_price_cents: 2,
        recorded_at: ~U[2026-03-03 10:00:00Z],
        subscription_id: g1.id
      },
      [tenant: @globex]
    ])

    a1 = draft_invoice("INV-A1", 1000, s1.id, @acme)
    a2 = draft_invoice("INV-A2", 505, s1.id, @acme)
    a3 = draft_invoice("INV-A3", 250, s1.id, @acme)

    line(a1.id, "setup", 1, 600, 600, @acme)
    line(a1.id, "support", 2, 200, 400, @acme)
    line(a2.id, "misc", 1, 500, 500, @acme)

    d(:issue_invoice!, [a1, [tenant: @acme]])
    d(:issue_invoice!, [a2, [tenant: @acme]])

    q1 = d(:create_tag!, ["q1", [tenant: @acme]])
    d(:create_tag!, ["vip", [tenant: @acme]])
    d(:tag_invoice!, [a1.id, q1.id, [tenant: @acme]])
    d(:tag_invoice!, [a3.id, q1.id, [tenant: @acme]])

    :ok
  end

  defp draft_invoice(number, total, subscription_id, tenant) do
    @invoice
    |> Ash.Changeset.for_create(
      :draft,
      %{number: number, total_cents: total, subscription_id: subscription_id},
      tenant: tenant
    )
    |> Ash.create!()
  end

  defp line(invoice_id, description, quantity, unit_cents, amount_cents, tenant) do
    @invoice_line
    |> Ash.Changeset.for_create(
      :create,
      %{
        description: description,
        quantity: quantity,
        unit_cents: unit_cents,
        amount_cents: amount_cents,
        invoice_id: invoice_id
      },
      tenant: tenant
    )
    |> Ash.create!()
  end

  # ------------------------------------------------------------------ contracts

  test "T01 Billing.Tenancy maps organisation slugs to postgres schema names" do
    assert apply(@tenancy, :schema_name, ["acme"]) == "tenant_acme"
    assert apply(@tenancy, :schema_name, ["globex"]) == "tenant_globex"
    assert apply(@tenancy, :slug_from_schema, ["tenant_acme"]) == "acme"
  end

  test "T02 tenant resources use context multitenancy and global resources use none" do
    for resource <- [@subscription, @usage_record, @invoice, @invoice_line, @tag_res, @invoice_tag] do
      assert Ash.Resource.Info.multitenancy_strategy(resource) == :context,
             "#{inspect(resource)} must use the :context multitenancy strategy"
    end

    for resource <- [@organisation, @plan_rate] do
      assert Ash.Resource.Info.multitenancy_strategy(resource) == nil,
             "#{inspect(resource)} must be global (no multitenancy)"
    end
  end

  test "T03 every resource is backed by AshPostgres.DataLayer, Billing.Repo and its stated table" do
    expected = [
      {@organisation, "organisations"},
      {@plan_rate, "plan_rates"},
      {@subscription, "subscriptions"},
      {@usage_record, "usage_records"},
      {@invoice, "invoices"},
      {@invoice_line, "invoice_lines"},
      {@tag_res, "tags"},
      {@invoice_tag, "invoice_tags"}
    ]

    for {resource, table} <- expected do
      assert Ash.Resource.Info.data_layer(resource) == AshPostgres.DataLayer
      assert AshPostgres.DataLayer.Info.table(resource) == table
      assert AshPostgres.DataLayer.Info.repo(resource, :read) == @repo
    end
  end

  test "T04 the repo declares the required postgres extensions" do
    extensions = apply(@repo, :installed_extensions, [])
    assert "pg_trgm" in extensions
    assert "ash-functions" in extensions
  end

  test "T05 tenant tables live only in tenant migrations, never in the public schema" do
    public_tables =
      rows("""
      select table_name from information_schema.tables
      where table_schema = 'public' and table_type = 'BASE TABLE'
      """)
      |> List.flatten()
      |> Enum.sort()

    assert "organisations" in public_tables
    assert "plan_rates" in public_tables

    for forbidden <- ~w(subscriptions usage_records invoices invoice_lines tags invoice_tags) do
      refute forbidden in public_tables,
             "#{forbidden} must not exist in the public schema"
    end
  end

  test "T06 the tenant migration path recreates every tenant table in a fresh schema" do
    apply(@repo, :query!, ["DROP SCHEMA IF EXISTS tenant_probe CASCADE", []])
    apply(@repo, :query!, ["CREATE SCHEMA tenant_probe", []])

    path = Ecto.Migrator.migrations_path(@repo, "tenant_migrations")
    assert File.dir?(path), "priv/repo/tenant_migrations must exist"
    assert Enum.any?(File.ls!(path), &String.ends_with?(&1, ".exs"))

    Ecto.Migrator.run(@repo, path, :up, all: true, prefix: "tenant_probe", log: false)

    tables =
      rows("""
      select table_name from information_schema.tables
      where table_schema = 'tenant_probe' and table_type = 'BASE TABLE'
      """)
      |> List.flatten()

    for expected <- ~w(subscriptions usage_records invoices invoice_lines tags invoice_tags) do
      assert expected in tables
    end
  end

  test "T07 Billing.Repo.all_tenants/0 lists one schema per organisation" do
    slugs = d(:list_organisations!, []) |> Enum.map(& &1.slug) |> Enum.sort()
    expected = Enum.map(slugs, &("tenant_" <> &1))

    assert Enum.sort(apply(@repo, :all_tenants, [])) == expected
    assert "tenant_acme" in expected
  end

  # --------------------------------------------------------- tenant provisioning

  test "T08 registering an organisation provisions its schema with every tenant table" do
    d(:register_organisation!, ["umbrella", "Umbrella Corp", "pro"])

    schemas =
      rows("select nspname from pg_namespace where nspname = 'tenant_umbrella'") |> List.flatten()

    assert schemas == ["tenant_umbrella"]

    tables =
      rows("""
      select table_name from information_schema.tables
      where table_schema = 'tenant_umbrella' and table_type = 'BASE TABLE'
      """)
      |> List.flatten()

    for expected <- ~w(subscriptions usage_records invoices invoice_lines tags invoice_tags) do
      assert expected in tables, "tenant_umbrella is missing #{expected}"
    end
  end

  test "T09 the same subscription code may exist in two tenants" do
    acme = sub_by("SUB-001", @acme)
    globex = sub_by("SUB-001", @globex)

    assert acme.monthly_cents == 5000
    assert globex.monthly_cents == 300
    refute acme.id == globex.id
  end

  test "T10 a duplicate subscription code inside one tenant is rejected" do
    assert {:error, %Ash.Error.Invalid{errors: errors}} =
             d(:open_subscription, [
               %{
                 code: "SUB-001",
                 plan_code: "pro",
                 monthly_cents: 1,
                 started_on: ~D[2026-01-01]
               },
               [tenant: @acme]
             ])

    assert Enum.any?(errors, fn error ->
             match?(%Ash.Error.Changes.InvalidAttribute{field: :code}, error) and
               error.message == "has already been taken"
           end)
  end

  test "T11 reading a tenant resource without a tenant raises Ash.Error.Invalid.TenantRequired" do
    assert {:error, %Ash.Error.Invalid{errors: errors}} = Ash.read(@subscription)

    assert Enum.any?(errors, fn error ->
             match?(%Ash.Error.Invalid.TenantRequired{resource: resource} when resource == @subscription, error)
           end)

    assert {:error, %Ash.Error.Invalid{errors: count_errors}} = Ash.count(@usage_record)
    assert Enum.any?(count_errors, &match?(%Ash.Error.Invalid.TenantRequired{}, &1))
  end

  test "T12 global resources are readable with no tenant and are not schema qualified" do
    {orgs, queries} = Harbor.Sql.capture(fn -> d(:list_organisations!, []) end)
    assert length(orgs) >= 3
    sql = Harbor.Sql.joined(queries)
    assert sql =~ ~s("organisations")
    refute sql =~ "tenant_"

    assert d(:list_plan_rates!, []) |> Enum.map(& &1.plan_code) |> Enum.sort() == ["free", "pro"]
  end

  test "T13 reads are scoped to the tenant schema" do
    assert @subscription
           |> Ash.Query.sort(code: :asc)
           |> Ash.read!(tenant: @acme)
           |> Enum.map(& &1.code) == ["SUB-001", "SUB-002", "ZED-777"]

    assert @subscription
           |> Ash.read!(tenant: @globex)
           |> Enum.map(& &1.code) == ["SUB-001"]
  end

  test "T14 a record of one tenant is invisible from another tenant" do
    globex_id = sub_by("SUB-001", @globex).id

    assert @subscription
           |> Ash.Query.filter(id == ^globex_id)
           |> Ash.read_one!(tenant: @acme) == nil
  end

  test "T15 aggregates and relationship loads are tenant scoped" do
    acme =
      @subscription
      |> Ash.Query.filter(code == "SUB-001")
      |> Ash.Query.load([:usage_record_count, :usage_records])
      |> Ash.read_one!(tenant: @acme)

    globex =
      @subscription
      |> Ash.Query.filter(code == "SUB-001")
      |> Ash.Query.load([:usage_record_count, :usage_records])
      |> Ash.read_one!(tenant: @globex)

    assert acme.usage_record_count == 3
    assert length(acme.usage_records) == 3
    assert globex.usage_record_count == 1
    assert length(globex.usage_records) == 1
  end

  test "T16 tenant rows are physically stored in their own schema" do
    assert rows("select count(*) from tenant_acme.subscriptions") == [[3]]
    assert rows("select count(*) from tenant_globex.subscriptions") == [[1]]

    assert rows("select code from tenant_globex.subscriptions") == [["SUB-001"]]

    assert rows("select count(*) from tenant_acme.usage_records") == [[4]]
    assert rows("select count(*) from tenant_globex.usage_records") == [[1]]
  end

  test "T17 tenant tables carry no tenant discriminator column" do
    columns =
      rows("""
      select column_name from information_schema.columns
      where table_schema = 'tenant_acme' and table_name = 'subscriptions'
      """)
      |> List.flatten()

    for required <- ~w(id code plan_code monthly_cents balance_cents status started_on) do
      assert required in columns
    end

    for column <- columns do
      refute String.contains?(column, "tenant"),
             "tenant_acme.subscriptions must not carry a tenant column (found #{column})"

      refute String.contains?(column, "organisation"),
             "tenant_acme.subscriptions must not carry an organisation column (found #{column})"
    end
  end

  test "T18 emitted SQL is schema qualified and never mentions another tenant" do
    {_result, queries} =
      Harbor.Sql.capture(fn ->
        @subscription |> Ash.Query.load([:usage_record_count]) |> Ash.read!(tenant: @acme)
      end)

    sql = Harbor.Sql.joined(queries)
    assert sql =~ ~s("tenant_acme"."subscriptions")
    assert sql =~ ~s("tenant_acme"."usage_records")
    refute sql =~ "tenant_globex"
  end

  test "T19 an Organisation struct can be used directly as the tenant" do
    org = d(:list_organisations!, []) |> Enum.find(&(&1.slug == "acme"))

    assert Ash.ToTenant.to_tenant(org, @subscription) == "tenant_acme"
    assert @subscription |> Ash.read!(tenant: org) |> length() == 3
  end

  # -------------------------------------------------------- SQL pushed compute

  test "T20 usage record calculations are computed from the stored columns" do
    records =
      @usage_record
      |> Ash.Query.filter(subscription_id == ^sub_by("SUB-001", @acme).id)
      |> Ash.Query.sort(recorded_at: :asc)
      |> Ash.Query.load([:line_total_cents, :recorded_month, :metric_label, :retention_until])
      |> Ash.read!(tenant: @acme)

    assert Enum.map(records, & &1.line_total_cents) == [360, 280, 90]
    assert Enum.map(records, & &1.recorded_month) == ["2026-03", "2026-03", "2026-04"]
    assert Enum.map(records, & &1.metric_label) == ["API_CALLS", "STORAGE", "API_CALLS"]

    assert Enum.map(records, & &1.retention_until) == [
             ~U[2026-04-15 10:00:00Z],
             ~U[2026-04-19 10:00:00Z],
             ~U[2026-05-24 10:00:00Z]
           ]
  end

  test "T21 usage record calculations are evaluated by postgres in a single query" do
    {records, queries} =
      Harbor.Sql.capture(fn ->
        @usage_record
        |> Ash.Query.load([:recorded_month, :metric_label, :retention_until])
        |> Ash.read!(tenant: @acme)
      end)

    assert length(records) == 4
    assert length(queries) == 1

    sql = Harbor.Sql.joined(queries)
    assert sql =~ "to_char("
    assert sql =~ "upper("
    assert String.downcase(sql) =~ "interval"
  end

  test "T22 filtering and sorting by calculations happens in postgres" do
    {records, queries} =
      Harbor.Sql.capture(fn ->
        @usage_record
        |> Ash.Query.filter(recorded_month == "2026-03")
        |> Ash.Query.sort(line_total_cents: :desc)
        |> Ash.read!(tenant: @acme)
      end)

    assert length(queries) == 1
    assert Enum.map(records, & &1.quantity) == [120, 40, 10]

    sql = Harbor.Sql.joined(queries)
    assert sql =~ "to_char("
    assert String.upcase(sql) =~ "ORDER BY"
  end

  test "T23 the search read action matches case insensitively via ILIKE" do
    assert d(:search_subscriptions!, ["sub-%", [tenant: @acme]])
           |> Enum.map(& &1.code)
           |> Enum.sort() == ["SUB-001", "SUB-002"]

    assert d(:search_subscriptions!, ["SUB-%", [tenant: @acme]]) |> length() == 2
    assert d(:search_subscriptions!, ["%zed%", [tenant: @acme]]) |> length() == 1

    {_result, queries} =
      Harbor.Sql.capture(fn -> d(:search_subscriptions!, ["sub-%", [tenant: @acme]]) end)

    assert String.downcase(Harbor.Sql.joined(queries)) =~ "ilike"
  end

  test "T24 the numbered read action matches case sensitively via LIKE" do
    hits =
      @invoice
      |> Ash.Query.for_read(:numbered, %{pattern: "INV-A%"})
      |> Ash.read!(tenant: @acme)

    assert length(hits) == 3

    assert @invoice
           |> Ash.Query.for_read(:numbered, %{pattern: "inv-a%"})
           |> Ash.read!(tenant: @acme) == []
  end

  test "T25 the fuzzy read action uses postgres trigram similarity" do
    {exact, queries} =
      Harbor.Sql.capture(fn -> d(:fuzzy_subscriptions!, ["SUB-001", 0.9, [tenant: @acme]]) end)

    assert Enum.map(exact, & &1.code) == ["SUB-001"]
    assert Harbor.Sql.joined(queries) =~ "similarity("

    loose = d(:fuzzy_subscriptions!, ["SUB-001", 0.3, [tenant: @acme]])
    codes = loose |> Enum.map(& &1.code) |> Enum.sort()
    assert "SUB-001" in codes
    assert "SUB-002" in codes
    refute "ZED-777" in codes
  end

  test "T26 subscription aggregates report the exact per tenant figures" do
    subscription =
      @subscription
      |> Ash.Query.filter(code == "SUB-001")
      |> Ash.Query.load([
        :usage_record_count,
        :pending_usage_count,
        :pending_quantity,
        :latest_metric,
        :issued_invoice_count,
        :issued_total_cents,
        :plan_unit_cents,
        :plan_included_units
      ])
      |> Ash.read_one!(tenant: @acme)

    assert subscription.usage_record_count == 3
    assert subscription.pending_usage_count == 3
    assert subscription.pending_quantity == 190
    assert subscription.latest_metric == "api_calls"
    assert subscription.issued_invoice_count == 2
    assert subscription.issued_total_cents == 1505
    assert subscription.plan_unit_cents == 25
    assert subscription.plan_included_units == 100
  end

  test "T27 empty relationships fall back to the declared aggregate defaults" do
    subscription =
      @subscription
      |> Ash.Query.filter(code == "ZED-777")
      |> Ash.Query.load([
        :usage_record_count,
        :pending_quantity,
        :latest_metric,
        :issued_invoice_count,
        :issued_total_cents,
        :plan_unit_cents
      ])
      |> Ash.read_one!(tenant: @acme)

    assert subscription.usage_record_count == 0
    assert subscription.pending_quantity == 0
    assert subscription.latest_metric == nil
    assert subscription.issued_invoice_count == 0
    assert subscription.issued_total_cents == 0
    assert subscription.plan_unit_cents == 40
  end

  test "T28 average_issued_cents composes two aggregates and rounds half up" do
    subscription =
      @subscription
      |> Ash.Query.filter(code == "SUB-001")
      |> Ash.Query.load([:average_issued_cents])
      |> Ash.read_one!(tenant: @acme)

    assert subscription.average_issued_cents == 753

    empty =
      @subscription
      |> Ash.Query.filter(code == "ZED-777")
      |> Ash.Query.load([:average_issued_cents])
      |> Ash.read_one!(tenant: @acme)

    assert empty.average_issued_cents == 0
  end

  test "T29 overage_cents is computed by the billing_overage_cents SQL function" do
    assert rows("""
           select count(*) from pg_proc where proname = 'billing_overage_cents'
           """) == [[1]]

    {subscriptions, queries} =
      Harbor.Sql.capture(fn ->
        @subscription
        |> Ash.Query.sort(code: :asc)
        |> Ash.Query.load([:overage_cents])
        |> Ash.read!(tenant: @acme)
      end)

    assert Enum.map(subscriptions, & &1.overage_cents) == [2250, 0, 0]
    assert Harbor.Sql.joined(queries) =~ "billing_overage_cents("

    globex =
      @subscription
      |> Ash.Query.load([:overage_cents])
      |> Ash.read!(tenant: @globex)

    assert Enum.map(globex, & &1.overage_cents) == [800]
  end

  test "T30 type/2 casts an integer column to text inside the query" do
    {subscription, queries} =
      Harbor.Sql.capture(fn ->
        @subscription
        |> Ash.Query.filter(code == "SUB-001")
        |> Ash.Query.load([:code_label, :monthly_label])
        |> Ash.read_one!(tenant: @acme)
      end)

    assert subscription.code_label == "SUB-001"
    assert subscription.monthly_label == "5000"
    assert Harbor.Sql.joined(queries) =~ "::text"
  end

  test "T31 the whole aggregate and calculation set loads in a single database query" do
    {subscriptions, queries} =
      Harbor.Sql.capture(fn ->
        @subscription
        |> Ash.Query.sort(code: :asc)
        |> Ash.Query.load([
          :usage_record_count,
          :pending_usage_count,
          :pending_quantity,
          :latest_metric,
          :issued_invoice_count,
          :issued_total_cents,
          :average_issued_cents,
          :overage_cents
        ])
        |> Ash.read!(tenant: @acme)
      end)

    assert length(subscriptions) == 3
    assert length(queries) == 1

    sql = Harbor.Sql.joined(queries)
    assert sql =~ "count("
    assert sql =~ "sum("
    assert sql =~ "billing_overage_cents("
  end

  test "T32 aggregates are usable as filters and run in SQL" do
    {hits, queries} =
      Harbor.Sql.capture(fn ->
        @subscription
        |> Ash.Query.filter(pending_quantity > 100)
        |> Ash.read!(tenant: @acme)
      end)

    assert Enum.map(hits, & &1.code) == ["SUB-001"]
    assert length(queries) == 1

    assert @subscription
           |> Ash.Query.filter(issued_total_cents > 1000)
           |> Ash.read!(tenant: @acme)
           |> Enum.map(& &1.code) == ["SUB-001"]
  end

  test "T33 an aggregate over a belongs_to joins the public schema" do
    {_subscriptions, queries} =
      Harbor.Sql.capture(fn ->
        @subscription
        |> Ash.Query.load([:plan_unit_cents])
        |> Ash.read!(tenant: @acme)
      end)

    assert Harbor.Sql.joined(queries) =~ ~s("public"."plan_rates")
  end

  test "T34 invoice aggregates and the aggregate derived calculation" do
    invoices =
      @invoice
      |> Ash.Query.sort(number: :asc)
      |> Ash.Query.load([:line_count, :lines_total_cents, :balanced, :number_label])
      |> Ash.read!(tenant: @acme)

    assert Enum.map(invoices, & &1.number) == ["INV-A1", "INV-A2", "INV-A3"]
    assert Enum.map(invoices, & &1.line_count) == [2, 1, 0]
    assert Enum.map(invoices, & &1.lines_total_cents) == [1000, 500, 0]
    assert Enum.map(invoices, & &1.balanced) == [true, false, false]
    assert Enum.map(invoices, & &1.number_label) == ["inv-a1", "inv-a2", "inv-a3"]
  end

  test "T35 aggregates over a many_to_many relationship" do
    {tags, queries} =
      Harbor.Sql.capture(fn ->
        @tag_res
        |> Ash.Query.sort(name: :asc)
        |> Ash.Query.load([:invoice_count, :invoiced_cents])
        |> Ash.read!(tenant: @acme)
      end)

    assert Enum.map(tags, & &1.name) == ["q1", "vip"]
    assert Enum.map(tags, & &1.invoice_count) == [2, 0]
    assert Enum.map(tags, & &1.invoiced_cents) == [1000, 0]
    assert length(queries) == 1
    assert Harbor.Sql.joined(queries) =~ ~s("tenant_acme"."invoice_tags")
  end

  # ------------------------------------------------------------- transactions

  test "T36 close_period bills every pending usage record in one transaction" do
    subscription = open_initech("CP-OK", 1000)
    usage(subscription.id, "api_calls", 5, 100, ~U[2026-05-01 09:00:00Z])
    usage(subscription.id, "storage", 3, 50, ~U[2026-05-02 09:00:00Z])

    assert {:ok, invoice} =
             d(:close_period, [subscription.id, "INV-CP-OK", 100_000, [tenant: @initech]])

    assert invoice.number == "INV-CP-OK"
    assert invoice.total_cents == 650
    assert invoice.status == :draft

    lines =
      @invoice_line
      |> Ash.Query.filter(invoice_id == ^invoice.id)
      |> Ash.Query.sort(amount_cents: :desc)
      |> Ash.read!(tenant: @initech)

    assert Enum.map(lines, & &1.amount_cents) == [500, 150]
    assert Enum.map(lines, & &1.description) == ["api_calls", "storage"]

    assert @usage_record
           |> Ash.Query.filter(subscription_id == ^subscription.id)
           |> Ash.read!(tenant: @initech)
           |> Enum.map(& &1.invoiced) == [true, true]
  end

  test "T37 a late failure inside close_period rolls back every write" do
    subscription = open_initech("CP-CAP", 1000)
    usage(subscription.id, "api_calls", 5, 100, ~U[2026-05-01 09:00:00Z])
    usage(subscription.id, "storage", 3, 50, ~U[2026-05-02 09:00:00Z])

    assert {:error, %Ash.Error.Invalid{errors: errors}} =
             d(:close_period, [subscription.id, "INV-CP-CAP", 100, [tenant: @initech]])

    assert Enum.any?(errors, fn error ->
             match?(%Ash.Error.Changes.InvalidArgument{field: :cap_cents}, error) and
               error.message == "period total exceeds cap"
           end)

    assert @invoice
           |> Ash.Query.filter(subscription_id == ^subscription.id)
           |> Ash.read!(tenant: @initech) == []

    assert rows(
             "select count(*) from tenant_initech.invoices where number = $1",
             ["INV-CP-CAP"]
           ) == [[0]]

    assert @usage_record
           |> Ash.Query.filter(subscription_id == ^subscription.id)
           |> Ash.read!(tenant: @initech)
           |> Enum.map(& &1.invoiced) == [false, false]
  end

  test "T38 close_period is declared transactional over every resource it touches" do
    action = Ash.Resource.Info.action(@invoice, :close_period)
    assert action.type == :action
    assert action.transaction? == true

    for resource <- [@invoice, @invoice_line, @usage_record] do
      assert resource in action.touches_resources
    end
  end

  test "T39 a successful issue runs before_action, after_action then after_transaction" do
    subscription = open_initech("ISS-OK", 0)
    invoice = draft_invoice("INV-ISS-OK", 400, subscription.id, @initech)

    apply(@trace, :reset, [])
    issued = d(:issue_invoice!, [invoice, [tenant: @initech]])

    assert issued.status == :issued
    assert issued.issued_on == Date.utc_today()

    assert apply(@trace, :entries, []) == [
             "issue:before_action",
             "issue:after_action",
             "issue:after_transaction:ok"
           ]
  end

  test "T40 an after_action failure rolls the update back and still runs after_transaction" do
    subscription = open_initech("ISS-BAD", 0)
    invoice = draft_invoice("INV-ISS-BAD", 0, subscription.id, @initech)

    apply(@trace, :reset, [])

    assert {:error, %Ash.Error.Invalid{errors: errors}} =
             d(:issue_invoice, [invoice, [tenant: @initech]])

    assert Enum.any?(errors, fn error ->
             match?(%Ash.Error.Changes.InvalidChanges{}, error) and
               error.message == "cannot issue an empty invoice"
           end)

    assert apply(@trace, :entries, []) == [
             "issue:before_action",
             "issue:after_action",
             "issue:after_transaction:error"
           ]

    reread = invoice_by("INV-ISS-BAD", @initech)
    assert reread.status == :draft
    assert reread.issued_on == nil
  end

  test "T41 concurrent spends are serialised by a row level lock" do
    subscription = open_initech("SPEND-RACE", 1000)

    outcomes =
      1..8
      |> Task.async_stream(
        fn _ -> d(:spend, [subscription.id, 300, [tenant: @initech]]) end,
        max_concurrency: 8,
        timeout: 60_000
      )
      |> Enum.map(fn {:ok, result} -> elem(result, 0) end)

    assert Enum.count(outcomes, &(&1 == :ok)) == 3
    assert Enum.count(outcomes, &(&1 == :error)) == 5

    reread = sub_by("SPEND-RACE", @initech)
    assert reread.balance_cents == 100
  end

  test "T42 spending more than the balance fails without changing the balance" do
    subscription = open_initech("SPEND-LOW", 50)

    assert {:error, %Ash.Error.Invalid{errors: errors}} =
             d(:spend, [subscription.id, 100, [tenant: @initech]])

    assert Enum.any?(errors, fn error ->
             match?(%Ash.Error.Changes.InvalidArgument{field: :amount_cents}, error) and
               error.message == "insufficient balance"
           end)

    assert sub_by("SPEND-LOW", @initech).balance_cents == 50
    assert {:ok, 20} = d(:spend, [subscription.id, 30, [tenant: @initech]])
    assert sub_by("SPEND-LOW", @initech).balance_cents == 20
  end

  test "T43 spend selects the row FOR UPDATE inside a transaction" do
    subscription = open_initech("SPEND-SQL", 500)

    {result, queries} =
      Harbor.Sql.capture(fn -> d(:spend, [subscription.id, 100, [tenant: @initech]]) end)

    assert result == {:ok, 400}

    sql = Harbor.Sql.joined(queries)
    assert String.upcase(sql) =~ "FOR UPDATE"
    assert sql =~ ~s("tenant_initech"."subscriptions")
  end

  test "T44 spending in one tenant never touches another tenant's row" do
    before_acme = sub_by("SUB-001", @acme).balance_cents
    globex = sub_by("SUB-001", @globex)

    assert {:ok, remaining} = d(:spend, [globex.id, 300, [tenant: @globex]])
    assert remaining == globex.balance_cents - 300

    assert sub_by("SUB-001", @acme).balance_cents == before_acme
  end

  defp open_initech(code, balance) do
    d(:open_subscription!, [
      %{
        code: code,
        plan_code: "free",
        monthly_cents: 100,
        balance_cents: balance,
        started_on: ~D[2026-05-01]
      },
      [tenant: @initech]
    ])
  end

  defp usage(subscription_id, metric, quantity, unit_price_cents, at) do
    d(:record_usage!, [
      %{
        metric: metric,
        quantity: quantity,
        unit_price_cents: unit_price_cents,
        recorded_at: at,
        subscription_id: subscription_id
      },
      [tenant: @initech]
    ])
  end
end

ExUnit.run()
'''


def _env():
    env = dict(os.environ)
    env["MIX_ENV"] = "dev"
    env["HEX_OFFLINE"] = "1"
    return env


def _run(args, timeout=900, cwd=PROJECT_DIR):
    return subprocess.run(
        args,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=_env(),
    )


def _tail(text, limit=4000):
    text = text or ""
    return text[-limit:]


@pytest.fixture(scope="session")
def suite():
    """Resets the database, runs the ExUnit suite and returns {scenario_id: (status, detail)}."""
    diagnostics = []

    started = _run(["pg-start"], timeout=300)
    if started.returncode != 0:
        return {}, f"`pg-start` failed:\nSTDOUT {_tail(started.stdout)}\nSTDERR {_tail(started.stderr)}"

    compiled = _run(["mix", "compile"], timeout=900)
    diagnostics.append(f"mix compile rc={compiled.returncode}\n{_tail(compiled.stdout)}\n{_tail(compiled.stderr)}")
    if compiled.returncode != 0:
        return {}, "The project does not compile.\n" + diagnostics[-1]

    dropped = _run(
        [
            "psql",
            "-h",
            "127.0.0.1",
            "-p",
            "5432",
            "-U",
            "postgres",
            "-d",
            "postgres",
            "-c",
            "DROP DATABASE IF EXISTS billing_dev WITH (FORCE)",
        ],
        timeout=300,
    )
    if dropped.returncode != 0:
        return {}, f"Could not drop billing_dev:\n{_tail(dropped.stderr)}"

    created = _run(["mix", "ash_postgres.create"], timeout=600)
    if created.returncode != 0:
        return {}, (
            "`mix ash_postgres.create` failed.\n"
            f"STDOUT {_tail(created.stdout)}\nSTDERR {_tail(created.stderr)}"
        )

    migrated = _run(["mix", "ash_postgres.migrate"], timeout=900)
    if migrated.returncode != 0:
        return {}, (
            "`mix ash_postgres.migrate` failed; the committed migrations under "
            "priv/repo/migrations must apply cleanly.\n"
            f"STDOUT {_tail(migrated.stdout)}\nSTDERR {_tail(migrated.stderr)}"
        )

    with open(SUITE_PATH, "w") as handle:
        handle.write(SUITE_EXS.lstrip("\n"))

    run = _run(["mix", "run", SUITE_PATH], timeout=900)

    results = {}
    for line in run.stdout.splitlines():
        match = RESULT_RE.match(line.strip())
        if not match:
            continue
        name = match.group("name")
        detail = ""
        if match.group("detail"):
            try:
                detail = base64.b64decode(match.group("detail")).decode("utf-8", "replace")
            except Exception:  # pragma: no cover - defensive
                detail = match.group("detail")
        scenario = name.replace("test ", "", 1).split(" ", 1)[0]
        results[scenario] = (match.group("status"), detail)

    if not results:
        return {}, (
            "The ExUnit suite produced no results.\n"
            f"STDOUT {_tail(run.stdout)}\nSTDERR {_tail(run.stderr)}"
        )

    return results, ""


def _check(suite, scenario):
    results, failure = suite
    if not results:
        pytest.fail(f"[{scenario}] the verification suite could not run. {failure}")
    assert scenario in results, (
        f"[{scenario}] did not report a result. Reported scenarios: {sorted(results)}"
    )
    status, detail = results[scenario]
    assert status == "pass", f"[{scenario}] failed:\n{detail}"


def test_t01_tenancy_helper_maps_slugs_to_schema_names(suite):
    _check(suite, "T01")

def test_t02_tenant_resources_use_context_multitenancy(suite):
    _check(suite, "T02")

def test_t03_resources_are_wired_to_ash_postgres_and_their_tables(suite):
    _check(suite, "T03")

def test_t04_repo_declares_required_postgres_extensions(suite):
    _check(suite, "T04")

def test_t05_tenant_tables_are_absent_from_the_public_schema(suite):
    _check(suite, "T05")

def test_t06_tenant_migrations_recreate_every_table_in_a_fresh_schema(suite):
    _check(suite, "T06")

def test_t07_all_tenants_lists_one_schema_per_organisation(suite):
    _check(suite, "T07")

def test_t08_registering_an_organisation_provisions_its_schema(suite):
    _check(suite, "T08")

def test_t09_same_subscription_code_may_exist_in_two_tenants(suite):
    _check(suite, "T09")

def test_t10_duplicate_subscription_code_inside_one_tenant_is_rejected(suite):
    _check(suite, "T10")

def test_t11_reading_without_a_tenant_raises_tenant_required(suite):
    _check(suite, "T11")

def test_t12_global_resources_are_readable_without_a_tenant(suite):
    _check(suite, "T12")

def test_t13_reads_are_scoped_to_the_tenant_schema(suite):
    _check(suite, "T13")

def test_t14_records_of_one_tenant_are_invisible_from_another(suite):
    _check(suite, "T14")

def test_t15_aggregates_and_relationship_loads_are_tenant_scoped(suite):
    _check(suite, "T15")

def test_t16_tenant_rows_are_physically_stored_in_their_own_schema(suite):
    _check(suite, "T16")

def test_t17_tenant_tables_carry_no_tenant_discriminator_column(suite):
    _check(suite, "T17")

def test_t18_emitted_sql_is_schema_qualified_to_one_tenant(suite):
    _check(suite, "T18")

def test_t19_an_organisation_struct_can_be_used_as_the_tenant(suite):
    _check(suite, "T19")

def test_t20_usage_record_calculations_return_the_expected_values(suite):
    _check(suite, "T20")

def test_t21_usage_record_calculations_run_in_one_postgres_query(suite):
    _check(suite, "T21")

def test_t22_calculation_filter_and_sort_happen_in_postgres(suite):
    _check(suite, "T22")

def test_t23_search_action_matches_case_insensitively(suite):
    _check(suite, "T23")

def test_t24_numbered_action_matches_case_sensitively(suite):
    _check(suite, "T24")

def test_t25_fuzzy_action_uses_postgres_trigram_similarity(suite):
    _check(suite, "T25")

def test_t26_subscription_aggregates_report_exact_figures(suite):
    _check(suite, "T26")

def test_t27_empty_relationships_use_the_declared_defaults(suite):
    _check(suite, "T27")

def test_t28_average_issued_cents_composes_two_aggregates(suite):
    _check(suite, "T28")

def test_t29_overage_cents_calls_the_custom_sql_function(suite):
    _check(suite, "T29")

def test_t30_type_cast_renders_an_integer_as_text_in_sql(suite):
    _check(suite, "T30")

def test_t31_all_aggregates_and_calculations_load_in_one_query(suite):
    _check(suite, "T31")

def test_t32_aggregates_are_usable_as_query_filters(suite):
    _check(suite, "T32")

def test_t33_aggregate_over_belongs_to_joins_the_public_schema(suite):
    _check(suite, "T33")

def test_t34_invoice_aggregates_and_derived_calculation(suite):
    _check(suite, "T34")

def test_t35_aggregates_over_a_many_to_many_relationship(suite):
    _check(suite, "T35")

def test_t36_close_period_bills_pending_usage_in_one_transaction(suite):
    _check(suite, "T36")

def test_t37_close_period_rolls_back_every_write_on_a_late_failure(suite):
    _check(suite, "T37")

def test_t38_close_period_is_declared_transactional(suite):
    _check(suite, "T38")

def test_t39_successful_issue_runs_hooks_in_order(suite):
    _check(suite, "T39")

def test_t40_failed_issue_rolls_back_and_still_runs_after_transaction(suite):
    _check(suite, "T40")

def test_t41_concurrent_spends_are_serialised_by_a_row_lock(suite):
    _check(suite, "T41")

def test_t42_spending_more_than_the_balance_is_rejected(suite):
    _check(suite, "T42")

def test_t43_spend_locks_the_row_for_update(suite):
    _check(suite, "T43")

def test_t44_spending_in_one_tenant_never_touches_another(suite):
    _check(suite, "T44")
