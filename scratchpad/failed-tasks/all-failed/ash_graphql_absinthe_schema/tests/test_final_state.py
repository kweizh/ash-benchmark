import os
import re
import subprocess

import pytest

PROJECT_DIR = "/home/user/tracker"
SUITE_PATH = "/tmp/harbor_ash_graphql_final.exs"
MARKER = re.compile(r"^@@HARBOR@@(?P<name>.*?)@@(?P<status>pass|fail|skip)@@(?P<detail>.*)$")

EXUNIT_SUITE = r'''
defmodule HarborFormatter do
  @moduledoc false
  use GenServer

  def init(_opts), do: {:ok, %{}}

  def handle_cast({:test_finished, test}, state) do
    status =
      case test.state do
        nil -> "pass"
        {:skipped, _} -> "skip"
        {:excluded, _} -> "skip"
        _ -> "fail"
      end

    detail =
      case test.state do
        {:failed, failures} ->
          try do
            ExUnit.Formatter.format_test_failure(test, failures, 1, 120, fn _, msg -> msg end)
          rescue
            e -> "could not format failure: " <> Exception.message(e)
          end

        {:invalid, _} ->
          "test invalid (setup_all failed)"

        _ ->
          ""
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

defmodule GqlHelper do
  @moduledoc false

  def schema, do: Module.concat(["Tracker.GraphqlSchema"])

  def run(doc, opts \\ []) do
    case Absinthe.run(doc, schema(), opts) do
      {:ok, result} -> result
      {:error, reason} -> %{errors: [%{message: inspect(reason)}], data: nil}
    end
  end

  def data(doc, opts \\ []) do
    result = run(doc, opts)

    if Map.has_key?(result, :errors) do
      raise "unexpected top level errors: #{inspect(result[:errors], limit: :infinity)}"
    end

    result.data
  end

  def gid(type, id), do: Base.encode64("#{type}:#{id}")

  def field_names(type_name) do
    data("{ __type(name: \"#{type_name}\") { fields { name } } }")
    |> get_in(["__type", "fields"])
    |> Enum.map(& &1["name"])
    |> Enum.sort()
  end

  def input_field_names(type_name) do
    data("{ __type(name: \"#{type_name}\") { inputFields { name } } }")
    |> get_in(["__type", "inputFields"])
    |> Enum.map(& &1["name"])
    |> Enum.sort()
  end

  def enum_values(type_name) do
    data("{ __type(name: \"#{type_name}\") { enumValues { name } } }")
    |> get_in(["__type", "enumValues"])
    |> Enum.map(& &1["name"])
    |> Enum.sort()
  end

  def field_type(type_name, field) do
    data("""
    { __type(name: "#{type_name}") { fields { name type { kind name ofType { kind name } } } } }
    """)
    |> get_in(["__type", "fields"])
    |> Enum.find(&(&1["name"] == field))
    |> case do
      nil -> nil
      f -> f["type"]
    end
  end

  def titles(edges), do: Enum.map(edges, & &1["node"]["title"])
end

defmodule TrackerGraphqlTest do
  use ExUnit.Case, async: false

  import GqlHelper

  alias Tracker.Delivery.Seed

  setup do
    Seed.seed!()

    admin = Ash.get!(Tracker.Delivery.User, Seed.alice_id(), authorize?: false)
    member = Ash.get!(Tracker.Delivery.User, Seed.bob_id(), authorize?: false)

    {:ok, admin: admin, member: member}
  end

  # ---------------------------------------------------------------- schema shape

  test "T01 root query exposes exactly the required fields" do
    names =
      data("{ __schema { queryType { fields { name } } } }")
      |> get_in(["__schema", "queryType", "fields"])
      |> Enum.map(& &1["name"])
      |> Enum.sort()

    assert names == [
             "apiInfo",
             "auditSprint",
             "labels",
             "node",
             "project",
             "projects",
             "ticket",
             "ticketByReference",
             "ticketOrFail",
             "tickets",
             "topTicket",
             "users"
           ]
  end

  test "T02 root mutation exposes exactly the required fields" do
    names =
      data("{ __schema { mutationType { fields { name } } } }")
      |> get_in(["__schema", "mutationType", "fields"])
      |> Enum.map(& &1["name"])
      |> Enum.sort()

    assert names == [
             "archiveProject",
             "createProject",
             "createTicket",
             "destroyTicket",
             "freezeSprint",
             "updateTicket"
           ]
  end

  test "T03 Ticket object exposes renamed and hidden fields correctly" do
    assert field_names("Ticket") == [
             "assignee",
             "assigneeId",
             "id",
             "labels",
             "points",
             "project",
             "projectId",
             "riskScore",
             "sequence",
             "severity",
             "status",
             "title"
           ]
  end

  test "T04 Ticket.status is a non null TicketStatus enum" do
    assert field_type("Ticket", "status") == %{
             "kind" => "NON_NULL",
             "name" => nil,
             "ofType" => %{"kind" => "ENUM", "name" => "TicketStatus"}
           }

    assert enum_values("TicketStatus") == ["BLOCKED", "DONE", "IN_PROGRESS", "OPEN"]
  end

  test "T05 Ticket and Project implement Node, User does not" do
    interfaces = fn name ->
      data("{ __type(name: \"#{name}\") { interfaces { name } } }")
      |> get_in(["__type", "interfaces"])
      |> Enum.map(& &1["name"])
    end

    assert interfaces.("Ticket") == ["Node"]
    assert interfaces.("Project") == ["Node"]
    assert interfaces.("User") == []
  end

  test "T06 User object hides internal notes and exposes role as a String" do
    assert field_names("User") == ["assignedTickets", "displayName", "email", "id", "role"]

    assert field_type("User", "role") == %{
             "kind" => "NON_NULL",
             "name" => nil,
             "ofType" => %{"kind" => "SCALAR", "name" => "String"}
           }
  end

  test "T07 Project exposes the aggregate as a non null Int" do
    assert field_names("Project") == [
             "archived",
             "id",
             "name",
             "openTicketCount",
             "slug",
             "tickets"
           ]

    assert field_type("Project", "openTicketCount") == %{
             "kind" => "NON_NULL",
             "name" => nil,
             "ofType" => %{"kind" => "SCALAR", "name" => "Int"}
           }
  end

  test "T08 riskScore is a nullable Int field taking a weight argument" do
    field =
      data("""
      { __type(name: "Ticket") { fields { name args { name type { kind ofType { name } } } type { kind name } } } }
      """)
      |> get_in(["__type", "fields"])
      |> Enum.find(&(&1["name"] == "riskScore"))

    assert field["type"] == %{"kind" => "SCALAR", "name" => "Int"}
    assert Enum.map(field["args"], & &1["name"]) == ["weight"]

    assert Enum.map(field["args"], & &1["type"]) == [
             %{"kind" => "NON_NULL", "ofType" => %{"name" => "Int"}}
           ]
  end

  test "T09 tickets is a relay connection with the standard shape" do
    tickets_field =
      data("{ __schema { queryType { fields { name type { kind name } } } } }")
      |> get_in(["__schema", "queryType", "fields"])
      |> Enum.find(&(&1["name"] == "tickets"))

    assert tickets_field["type"]["name"] == "TicketConnection"

    assert field_names("TicketConnection") == ["count", "edges", "pageInfo"]
    assert field_names("TicketEdge") == ["cursor", "node"]

    assert field_type("TicketEdge", "cursor") == %{
             "kind" => "NON_NULL",
             "name" => nil,
             "ofType" => %{"kind" => "SCALAR", "name" => "String"}
           }

    assert field_type("TicketEdge", "node") == %{
             "kind" => "NON_NULL",
             "name" => nil,
             "ofType" => %{"kind" => "OBJECT", "name" => "Ticket"}
           }
  end

  test "T10 projects, labels and users are plain non paginated lists" do
    fields =
      data(
        "{ __schema { queryType { fields { name type { kind ofType { kind ofType { kind ofType { name } } } } } } } }"
      )
      |> get_in(["__schema", "queryType", "fields"])

    for {name, inner} <- [{"projects", "Project"}, {"labels", "Label"}, {"users", "User"}] do
      field = Enum.find(fields, &(&1["name"] == name))

      assert field["type"] == %{
               "kind" => "NON_NULL",
               "ofType" => %{
                 "kind" => "LIST",
                 "ofType" => %{
                   "kind" => "NON_NULL",
                   "ofType" => %{"name" => inner}
                 }
               }
             }
    end
  end

  test "T11 create input objects are derived with the required names" do
    assert input_field_names("CreateTicketInput") == [
             "assigneeId",
             "newLabels",
             "points",
             "projectId",
             "sequence",
             "severity",
             "status",
             "title"
           ]

    assert input_field_names("UpdateTicketInput") == [
             "assigneeId",
             "points",
             "severity",
             "status",
             "title"
           ]

    assert input_field_names("TicketLabelInput") == ["colour", "name"]
  end

  test "T12 Label filtering and sorting is restricted to name" do
    assert enum_values("LabelSortField") == ["NAME"]
    assert input_field_names("LabelFilterInput") == ["and", "name", "not", "or"]

    assert enum_values("TicketSortField") == [
             "ASSIGNEE_ID",
             "ID",
             "POINTS",
             "PROJECT_ID",
             "RISK_SCORE",
             "SEQUENCE",
             "SEVERITY",
             "STATUS",
             "TITLE"
           ]
  end

  test "T13 ticketOrFail is non null while ticket is nullable" do
    fields =
      data("{ __schema { queryType { fields { name type { kind name ofType { name } } } } } }")
      |> get_in(["__schema", "queryType", "fields"])

    assert Enum.find(fields, &(&1["name"] == "ticket"))["type"] == %{
             "kind" => "OBJECT",
             "name" => "Ticket",
             "ofType" => nil
           }

    assert Enum.find(fields, &(&1["name"] == "ticketOrFail"))["type"] == %{
             "kind" => "NON_NULL",
             "name" => nil,
             "ofType" => %{"name" => "Ticket"}
           }
  end

  test "T14 the generic action mutation returns a String result plus errors" do
    assert field_names("FreezeSprintResult") == ["errors", "result"]

    assert field_type("FreezeSprintResult", "result") == %{
             "kind" => "SCALAR",
             "name" => "String",
             "ofType" => nil
           }

    assert input_field_names("FreezeSprintInput") == ["reason", "slug"]
  end

  # ---------------------------------------------------------------- queries

  test "T15 the hand written apiInfo query works" do
    assert data("{ apiInfo { name ticketCount } }") == %{
             "apiInfo" => %{"name" => "tracker", "ticketCount" => 6}
           }
  end

  test "T16 ticket is fetched by its relay global id" do
    id = gid("ticket", Seed.ticket_id(1))

    assert data("{ ticket(id: \"#{id}\") { id title status points } }") == %{
             "ticket" => %{
               "id" => id,
               "title" => "Login fails on Safari",
               "status" => "OPEN",
               "points" => 3
             }
           }
  end

  test "T17 a raw uuid is rejected by the relay aware get query" do
    result = run("{ ticket(id: \"#{Seed.ticket_id(1)}\") { id } }")

    assert result.data == %{"ticket" => nil}
    assert [error] = result.errors
    assert error.code == "invalid_primary_key"
  end

  test "T18 node resolves Ticket and Project global ids" do
    ticket_id = gid("ticket", Seed.ticket_id(3))

    assert data("{ node(id: \"#{ticket_id}\") { id ... on Ticket { title severity } } }") == %{
             "node" => %{"id" => ticket_id, "title" => "Slow dashboard", "severity" => 4}
           }

    project_id = gid("project", Seed.apollo_id())

    assert data("{ node(id: \"#{project_id}\") { id ... on Project { name openTicketCount } } }") ==
             %{
               "node" => %{"id" => project_id, "name" => "Apollo", "openTicketCount" => 2}
             }
  end

  test "T19 topTicket read_one returns the single highest severity ticket" do
    assert data("{ topTicket { title severity } }") == %{
             "topTicket" => %{"title" => "Login fails on Safari", "severity" => 5}
           }
  end

  test "T20 projects exposes the filtered count aggregate" do
    assert data("{ projects { name slug archived openTicketCount } }") == %{
             "projects" => [
               %{
                 "name" => "Apollo",
                 "slug" => "apollo",
                 "archived" => false,
                 "openTicketCount" => 2
               },
               %{
                 "name" => "Zephyr",
                 "slug" => "zephyr",
                 "archived" => false,
                 "openTicketCount" => 1
               }
             ]
           }
  end

  test "T21 labels can be sorted by name" do
    assert data("{ labels(sort: [{field: NAME, order: ASC}]) { name colour } }") == %{
             "labels" => [
               %{"name" => "bug", "colour" => "#c0392b"},
               %{"name" => "perf", "colour" => "#16a085"},
               %{"name" => "ux", "colour" => "#8e44ad"}
             ]
           }
  end

  test "T22 hidden attributes are not part of the schema" do
    ticket_result = run("{ tickets(first: 1) { edges { node { internalReference } } } }")
    assert [%{message: message}] = ticket_result.errors
    assert message =~ "Cannot query field \"internalReference\" on type \"Ticket\"."

    user_result = run("{ users { internalNotes } }")
    assert [%{message: user_message}] = user_result.errors
    assert user_message =~ "Cannot query field \"internalNotes\" on type \"User\"."
  end

  test "T23 relationships and calculations resolve through a get query" do
    id = gid("ticket", Seed.ticket_id(3))

    assert data("""
           { ticket(id: "#{id}") {
               title
               riskScore(weight: 10)
               assignee { displayName role }
               project { slug openTicketCount }
               labels(sort: [{field: NAME, order: ASC}]) { name }
             } }
           """) == %{
             "ticket" => %{
               "title" => "Slow dashboard",
               "riskScore" => 48,
               "assignee" => %{"displayName" => "Alice", "role" => "admin"},
               "project" => %{"slug" => "apollo", "openTicketCount" => 2},
               "labels" => [%{"name" => "bug"}, %{"name" => "perf"}]
             }
           }
  end

  # ---------------------------------------------------------------- relay pagination

  test "T24 the first connection page reports the total count and page info" do
    page =
      data("""
      { tickets(first: 2, sort: [{field: SEQUENCE, order: ASC}]) {
          count
          edges { cursor node { title } }
          pageInfo { hasNextPage hasPreviousPage startCursor endCursor }
        } }
      """)["tickets"]

    assert page["count"] == 6
    assert titles(page["edges"]) == ["Login fails on Safari", "Improve empty state"]
    assert page["pageInfo"]["hasNextPage"] == true
    assert page["pageInfo"]["hasPreviousPage"] == false
    assert page["pageInfo"]["startCursor"] == List.first(page["edges"])["cursor"]
    assert page["pageInfo"]["endCursor"] == List.last(page["edges"])["cursor"]
  end

  test "T25 forward pagination walks the whole connection without gaps" do
    walk = fn walk, after_cursor, acc ->
      after_arg = if after_cursor, do: ", after: \"#{after_cursor}\"", else: ""

      page =
        data("""
        { tickets(first: 2#{after_arg}, sort: [{field: SEQUENCE, order: ASC}]) {
            edges { cursor node { title } }
            pageInfo { hasNextPage endCursor }
          } }
        """)["tickets"]

      acc = acc ++ titles(page["edges"])

      if page["pageInfo"]["hasNextPage"] do
        walk.(walk, page["pageInfo"]["endCursor"], acc)
      else
        acc
      end
    end

    assert walk.(walk, nil, []) == [
             "Login fails on Safari",
             "Improve empty state",
             "Slow dashboard",
             "Broken CSV export",
             "Update docs",
             "Zephyr smoke test"
           ]
  end

  test "T26 an edge cursor can be used as the after argument" do
    page =
      data("""
      { tickets(first: 3, sort: [{field: SEQUENCE, order: ASC}]) { edges { cursor node { title } } } }
      """)["tickets"]

    cursor = Enum.at(page["edges"], 1)["cursor"]

    next =
      data("""
      { tickets(first: 2, after: "#{cursor}", sort: [{field: SEQUENCE, order: ASC}]) {
          edges { node { title } }
          pageInfo { hasPreviousPage hasNextPage }
        } }
      """)["tickets"]

    assert titles(next["edges"]) == ["Slow dashboard", "Broken CSV export"]
    assert next["pageInfo"]["hasPreviousPage"] == true
    assert next["pageInfo"]["hasNextPage"] == true
  end

  test "T27 a ticket created through the api shows up at the end of the connection" do
    created =
      data("""
      mutation { createTicket(input: {title: "Freshly added", projectId: "#{gid("project", Seed.apollo_id())}", sequence: 99}) {
        result { id }
        errors { code }
      } }
      """)

    assert created["createTicket"]["errors"] == []

    page =
      data("""
      { tickets(first: 10, sort: [{field: SEQUENCE, order: ASC}]) { count edges { node { title } } } }
      """)["tickets"]

    assert page["count"] == 7
    assert List.last(titles(page["edges"])) == "Freshly added"
  end

  test "T28 the connection honours a filter and reports the filtered count" do
    page =
      data("""
      { tickets(filter: {status: {eq: OPEN}}, sort: [{field: SEQUENCE, order: ASC}], first: 10) {
          count
          edges { node { title status } }
        } }
      """)["tickets"]

    assert page["count"] == 3
    assert titles(page["edges"]) == ["Login fails on Safari", "Slow dashboard", "Zephyr smoke test"]
  end

  # ---------------------------------------------------------------- filtering & sorting

  test "T29 boolean filter combinators are derived from the resource" do
    page =
      data("""
      { tickets(filter: {and: [{status: {notEq: DONE}}, {severity: {greaterThan: 1}}]},
                sort: [{field: SEVERITY, order: DESC}, {field: SEQUENCE, order: ASC}],
                first: 10) {
          count
          edges { node { title severity } }
        } }
      """)["tickets"]

    assert page["count"] == 5

    assert titles(page["edges"]) == [
             "Login fails on Safari",
             "Slow dashboard",
             "Broken CSV export",
             "Improve empty state",
             "Zephyr smoke test"
           ]
  end

  test "T30 an or filter is supported" do
    page =
      data("""
      { tickets(filter: {or: [{status: {eq: BLOCKED}}, {status: {eq: DONE}}]},
                sort: [{field: SEQUENCE, order: ASC}], first: 10) {
          edges { node { title } }
        } }
      """)["tickets"]

    assert titles(page["edges"]) == ["Broken CSV export", "Update docs"]
  end

  test "T31 the renamed attribute is filterable and sortable under its graphql name" do
    page =
      data("""
      { tickets(filter: {points: {greaterThanOrEqual: 8}}, sort: [{field: POINTS, order: DESC}], first: 10) {
          edges { node { title points } }
        } }
      """)["tickets"]

    assert Enum.map(page["edges"], &{&1["node"]["title"], &1["node"]["points"]}) == [
             {"Zephyr smoke test", 13},
             {"Slow dashboard", 8}
           ]
  end

  test "T32 filtering across a relationship works" do
    page =
      data("""
      { tickets(filter: {project: {slug: {eq: "zephyr"}}}, sort: [{field: SEQUENCE, order: ASC}], first: 10) {
          count
          edges { node { title } }
        } }
      """)["tickets"]

    assert page["count"] == 1
    assert titles(page["edges"]) == ["Zephyr smoke test"]
  end

  test "T33 the calculation can be used as a sort key with its argument" do
    page =
      data("""
      { tickets(sort: [{field: RISK_SCORE, order: DESC, riskScoreInput: {weight: 10}}], first: 3) {
          edges { node { title riskScore(weight: 10) } }
        } }
      """)["tickets"]

    assert Enum.map(page["edges"], &{&1["node"]["title"], &1["node"]["riskScore"]}) == [
             {"Login fails on Safari", 53},
             {"Slow dashboard", 48},
             {"Zephyr smoke test", 33}
           ]
  end

  # ---------------------------------------------------------------- mutations

  test "T34 createTicket returns the created record and an empty error list" do
    result =
      data("""
      mutation { createTicket(input: {
          title: "Add rate limiting",
          projectId: "#{gid("project", Seed.apollo_id())}",
          status: BLOCKED,
          severity: 4,
          points: 5,
          sequence: 50,
          assigneeId: "#{gid("user", Seed.bob_id())}"
        }) {
        result { title status severity points sequence assignee { displayName } project { slug } }
        errors { code }
      } }
      """)["createTicket"]

    assert result["errors"] == []

    assert result["result"] == %{
             "title" => "Add rate limiting",
             "status" => "BLOCKED",
             "severity" => 4,
             "points" => 5,
             "sequence" => 50,
             "assignee" => %{"displayName" => "Bob"},
             "project" => %{"slug" => "apollo"}
           }
  end

  test "T35 the managed relationship input creates and links labels" do
    result =
      data("""
      mutation { createTicket(input: {
          title: "Flaky integration suite",
          projectId: "#{gid("project", Seed.apollo_id())}",
          sequence: 51,
          newLabels: [{name: "regression", colour: "#111111"}, {name: "ci"}]
        }) {
        result { title labels(sort: [{field: NAME, order: ASC}]) { name colour } }
        errors { code message }
      } }
      """)["createTicket"]

    assert result["errors"] == []

    assert result["result"]["labels"] == [
             %{"name" => "ci", "colour" => nil},
             %{"name" => "regression", "colour" => "#111111"}
           ]

    assert data("{ labels(sort: [{field: NAME, order: ASC}]) { name } }") == %{
             "labels" => [
               %{"name" => "bug"},
               %{"name" => "ci"},
               %{"name" => "perf"},
               %{"name" => "regression"},
               %{"name" => "ux"}
             ]
           }
  end

  test "T36 a validation failure is reported inside the mutation result" do
    result =
      run("""
      mutation { createTicket(input: {title: "ab", projectId: "#{gid("project", Seed.apollo_id())}", sequence: 52}) {
        result { title }
        errors { code fields message shortMessage vars path }
      } }
      """)

    refute Map.has_key?(result, :errors)

    payload = result.data["createTicket"]
    assert payload["result"] == nil

    assert payload["errors"] == [
             %{
               "code" => "invalid_attribute",
               "fields" => ["title"],
               "message" => "must be at least 3 characters",
               "shortMessage" => "must be at least 3 characters",
               "vars" => %{min: 3},
               "path" => ["input", "title"]
             }
           ]

    assert data("{ apiInfo { ticketCount } }") == %{"apiInfo" => %{"ticketCount" => 6}}
  end

  test "T37 updateTicket applies changes and reports validation failures" do
    id = gid("ticket", Seed.ticket_id(4))

    ok =
      data("""
      mutation { updateTicket(id: "#{id}", input: {status: DONE, points: 7}) {
        result { id title status points }
        errors { code }
      } }
      """)["updateTicket"]

    assert ok["errors"] == []

    assert ok["result"] == %{
             "id" => id,
             "title" => "Broken CSV export",
             "status" => "DONE",
             "points" => 7
           }

    bad =
      data("""
      mutation { updateTicket(id: "#{id}", input: {title: "no"}) {
        result { id }
        errors { code fields message }
      } }
      """)["updateTicket"]

    assert bad["result"] == nil

    assert bad["errors"] == [
             %{
               "code" => "invalid_attribute",
               "fields" => ["title"],
               "message" => "must be at least 3 characters"
             }
           ]
  end

  test "T38 updating a missing record yields a not_found error in the result" do
    missing = gid("ticket", "cccccccc-0000-0000-0000-000000000099")

    payload =
      data("""
      mutation { updateTicket(id: "#{missing}", input: {title: "whatever"}) {
        result { id }
        errors { code fields message }
      } }
      """)["updateTicket"]

    assert payload["result"] == nil

    assert payload["errors"] == [
             %{"code" => "not_found", "fields" => ["id"], "message" => "could not be found"}
           ]
  end

  test "T39 destroying a ticket removes it and ticketOrFail then errors at the top level" do
    created =
      data("""
      mutation { createTicket(input: {title: "Temporary ticket", projectId: "#{gid("project", Seed.apollo_id())}", sequence: 60}) {
        result { id }
        errors { code }
      } }
      """)["createTicket"]

    id = created["result"]["id"]

    destroyed =
      data("""
      mutation { destroyTicket(id: "#{id}") { result { id title } errors { code } } }
      """)["destroyTicket"]

    assert destroyed["errors"] == []
    assert destroyed["result"] == %{"id" => id, "title" => "Temporary ticket"}

    result = run("{ ticketOrFail(id: \"#{id}\") { id } }")
    assert result.data == nil
    assert [error] = result.errors
    assert error.code == "not_found"
  end

  test "T40 archiveProject is forbidden without an admin actor", %{
    admin: admin,
    member: member
  } do
    id = gid("project", Seed.zephyr_id())

    doc = """
    mutation { archiveProject(id: "#{id}") {
      result { slug archived }
      errors { code message shortMessage fields }
    } }
    """

    anonymous = data(doc)["archiveProject"]
    assert anonymous["result"] == nil

    assert anonymous["errors"] == [
             %{
               "code" => "forbidden",
               "message" => "forbidden",
               "shortMessage" => "forbidden",
               "fields" => []
             }
           ]

    as_member = data(doc, context: %{actor: member})["archiveProject"]
    assert as_member["result"] == nil
    assert Enum.map(as_member["errors"], & &1["code"]) == ["forbidden"]

    as_admin = data(doc, context: %{actor: admin})["archiveProject"]
    assert as_admin["errors"] == []
    assert as_admin["result"] == %{"slug" => "zephyr", "archived" => true}
  end

  test "T41 the generic action mutation returns its string result" do
    payload =
      data("""
      mutation { freezeSprint(input: {slug: "apollo", reason: "release"}) {
        result
        errors { code }
      } }
      """)["freezeSprint"]

    assert payload["errors"] == []
    assert payload["result"] == "frozen:apollo:release"

    missing =
      data("""
      mutation { freezeSprint(input: {slug: "nope", reason: "release"}) {
        result
        errors { code message }
      } }
      """)["freezeSprint"]

    assert missing["result"] == nil
    assert Enum.map(missing["errors"], & &1["code"]) == ["not_found"]
  end

  test "T42 the custom exception surfaces through the AshGraphql.Error protocol", %{admin: admin} do
    _ =
      data(
        """
        mutation { archiveProject(id: "#{gid("project", Seed.zephyr_id())}") { result { archived } errors { code } } }
        """,
        context: %{actor: admin}
      )

    payload =
      data("""
      mutation { freezeSprint(input: {slug: "zephyr", reason: "release"}) {
        result
        errors { code message shortMessage fields vars }
      } }
      """)["freezeSprint"]

    assert payload["result"] == nil

    assert payload["errors"] == [
             %{
               "code" => "sprint_frozen",
               "message" => "sprint zephyr is already frozen",
               "shortMessage" => "sprint frozen",
               "fields" => ["reason"],
               "vars" => %{project_slug: "zephyr"}
             }
           ]
  end

  test "T43 raised errors are shown because the domain enables them" do
    result = run("{ auditSprint(slug: \"apollo\") }")

    assert result.data == nil
    assert [%{message: message}] = result.errors
    assert message =~ "audit backend offline for apollo"
  end

  # ---------------------------------------------------------------- custom resolver

  test "T44 the hand written ticketByReference query loads requested fields" do
    assert data("""
           { ticketByReference(reference: "APOLLO-3") {
               id
               title
               riskScore(weight: 10)
               labels(sort: [{field: NAME, order: ASC}]) { name }
               project { slug openTicketCount }
               assignee { displayName }
             } }
           """) == %{
             "ticketByReference" => %{
               "id" => gid("ticket", Seed.ticket_id(3)),
               "title" => "Slow dashboard",
               "riskScore" => 48,
               "labels" => [%{"name" => "bug"}, %{"name" => "perf"}],
               "project" => %{"slug" => "apollo", "openTicketCount" => 2},
               "assignee" => %{"displayName" => "Alice"}
             }
           }

    missing = run("{ ticketByReference(reference: \"NOPE-1\") { id title } }")

    refute Map.has_key?(missing, :errors)
    assert missing.data == %{"ticketByReference" => nil}
  end
end

ExUnit.run()
'''


@pytest.fixture(scope="session")
def suite_results():
    with open(SUITE_PATH, "w") as handle:
        handle.write(EXUNIT_SUITE.lstrip("\n"))

    env = os.environ.copy()
    env["MIX_ENV"] = "dev"

    try:
        completed = subprocess.run(
            ["mix", "run", SUITE_PATH],
            cwd=PROJECT_DIR,
            capture_output=True,
            text=True,
            timeout=1800,
            env=env,
        )
    finally:
        if os.path.exists(SUITE_PATH):
            os.remove(SUITE_PATH)

    output = completed.stdout + "\n" + completed.stderr

    results = {}
    for line in output.splitlines():
        match = MARKER.match(line.strip())
        if not match:
            continue
        parts = match.group("name").split()
        if parts and parts[0] == "test" and len(parts) > 1:
            key = parts[1]
        elif parts:
            key = parts[0]
        else:
            continue
        results[key] = (match.group("status"), match.group("detail"))

    if not results:
        raise AssertionError(
            "The ExUnit bridge produced no results. The project most likely failed to "
            "compile or Tracker.GraphqlSchema could not be loaded.\n"
            "returncode: {}\nstdout tail:\n{}\nstderr tail:\n{}".format(
                completed.returncode, completed.stdout[-8000:], completed.stderr[-8000:]
            )
        )

    return results


def _assert_scenario(suite_results, scenario_id, description):
    entry = suite_results.get(scenario_id)
    assert entry is not None, (
        "Scenario {} ({}) did not run at all. Collected scenarios: {}".format(
            scenario_id, description, sorted(suite_results)
        )
    )
    status, detail = entry
    if status == "pass":
        return

    import base64

    try:
        rendered = base64.b64decode(detail).decode("utf-8", "replace")
    except Exception:
        rendered = detail

    raise AssertionError(
        "Scenario {} ({}) failed:\n{}".format(scenario_id, description, rendered)
    )


def test_t01_root_query_exposes_exactly_the_required_fields(suite_results):
    _assert_scenario(suite_results, "T01", 'root query exposes exactly the required fields')


def test_t02_root_mutation_exposes_exactly_the_required_fields(suite_results):
    _assert_scenario(suite_results, "T02", 'root mutation exposes exactly the required fields')


def test_t03_ticket_object_exposes_renamed_and_hidden_fields_correctly(suite_results):
    _assert_scenario(suite_results, "T03", 'Ticket object exposes renamed and hidden fields correctly')


def test_t04_ticket_status_is_a_non_null_ticketstatus_enum(suite_results):
    _assert_scenario(suite_results, "T04", 'Ticket.status is a non null TicketStatus enum')


def test_t05_ticket_and_project_implement_node_user_does_not(suite_results):
    _assert_scenario(suite_results, "T05", 'Ticket and Project implement Node, User does not')


def test_t06_user_object_hides_internal_notes_and_exposes_role_as_a_string(suite_results):
    _assert_scenario(suite_results, "T06", 'User object hides internal notes and exposes role as a String')


def test_t07_project_exposes_the_aggregate_as_a_non_null_int(suite_results):
    _assert_scenario(suite_results, "T07", 'Project exposes the aggregate as a non null Int')


def test_t08_riskscore_is_a_nullable_int_field_taking_a_weight_argument(suite_results):
    _assert_scenario(suite_results, "T08", 'riskScore is a nullable Int field taking a weight argument')


def test_t09_tickets_is_a_relay_connection_with_the_standard_shape(suite_results):
    _assert_scenario(suite_results, "T09", 'tickets is a relay connection with the standard shape')


def test_t10_projects_labels_and_users_are_plain_non_paginated_lists(suite_results):
    _assert_scenario(suite_results, "T10", 'projects, labels and users are plain non paginated lists')


def test_t11_create_input_objects_are_derived_with_the_required_names(suite_results):
    _assert_scenario(suite_results, "T11", 'create input objects are derived with the required names')


def test_t12_label_filtering_and_sorting_is_restricted_to_name(suite_results):
    _assert_scenario(suite_results, "T12", 'Label filtering and sorting is restricted to name')


def test_t13_ticketorfail_is_non_null_while_ticket_is_nullable(suite_results):
    _assert_scenario(suite_results, "T13", 'ticketOrFail is non null while ticket is nullable')


def test_t14_the_generic_action_mutation_returns_a_string_result_plus_errors(suite_results):
    _assert_scenario(suite_results, "T14", 'the generic action mutation returns a String result plus errors')


def test_t15_the_hand_written_apiinfo_query_works(suite_results):
    _assert_scenario(suite_results, "T15", 'the hand written apiInfo query works')


def test_t16_ticket_is_fetched_by_its_relay_global_id(suite_results):
    _assert_scenario(suite_results, "T16", 'ticket is fetched by its relay global id')


def test_t17_a_raw_uuid_is_rejected_by_the_relay_aware_get_query(suite_results):
    _assert_scenario(suite_results, "T17", 'a raw uuid is rejected by the relay aware get query')


def test_t18_node_resolves_ticket_and_project_global_ids(suite_results):
    _assert_scenario(suite_results, "T18", 'node resolves Ticket and Project global ids')


def test_t19_topticket_read_one_returns_the_single_highest_severity_ticket(suite_results):
    _assert_scenario(suite_results, "T19", 'topTicket read_one returns the single highest severity ticket')


def test_t20_projects_exposes_the_filtered_count_aggregate(suite_results):
    _assert_scenario(suite_results, "T20", 'projects exposes the filtered count aggregate')


def test_t21_labels_can_be_sorted_by_name(suite_results):
    _assert_scenario(suite_results, "T21", 'labels can be sorted by name')


def test_t22_hidden_attributes_are_not_part_of_the_schema(suite_results):
    _assert_scenario(suite_results, "T22", 'hidden attributes are not part of the schema')


def test_t23_relationships_and_calculations_resolve_through_a_get_query(suite_results):
    _assert_scenario(suite_results, "T23", 'relationships and calculations resolve through a get query')


def test_t24_the_first_connection_page_reports_the_total_count_and_page_info(suite_results):
    _assert_scenario(suite_results, "T24", 'the first connection page reports the total count and page info')


def test_t25_forward_pagination_walks_the_whole_connection_without_gaps(suite_results):
    _assert_scenario(suite_results, "T25", 'forward pagination walks the whole connection without gaps')


def test_t26_an_edge_cursor_can_be_used_as_the_after_argument(suite_results):
    _assert_scenario(suite_results, "T26", 'an edge cursor can be used as the after argument')


def test_t27_a_ticket_created_through_the_api_shows_up_at_the_end_of_the_connection(suite_results):
    _assert_scenario(suite_results, "T27", 'a ticket created through the api shows up at the end of the connection')


def test_t28_the_connection_honours_a_filter_and_reports_the_filtered_count(suite_results):
    _assert_scenario(suite_results, "T28", 'the connection honours a filter and reports the filtered count')


def test_t29_boolean_filter_combinators_are_derived_from_the_resource(suite_results):
    _assert_scenario(suite_results, "T29", 'boolean filter combinators are derived from the resource')


def test_t30_an_or_filter_is_supported(suite_results):
    _assert_scenario(suite_results, "T30", 'an or filter is supported')


def test_t31_the_renamed_attribute_is_filterable_and_sortable_under_its_graphql_name(suite_results):
    _assert_scenario(suite_results, "T31", 'the renamed attribute is filterable and sortable under its graphql name')


def test_t32_filtering_across_a_relationship_works(suite_results):
    _assert_scenario(suite_results, "T32", 'filtering across a relationship works')


def test_t33_the_calculation_can_be_used_as_a_sort_key_with_its_argument(suite_results):
    _assert_scenario(suite_results, "T33", 'the calculation can be used as a sort key with its argument')


def test_t34_createticket_returns_the_created_record_and_an_empty_error_list(suite_results):
    _assert_scenario(suite_results, "T34", 'createTicket returns the created record and an empty error list')


def test_t35_the_managed_relationship_input_creates_and_links_labels(suite_results):
    _assert_scenario(suite_results, "T35", 'the managed relationship input creates and links labels')


def test_t36_a_validation_failure_is_reported_inside_the_mutation_result(suite_results):
    _assert_scenario(suite_results, "T36", 'a validation failure is reported inside the mutation result')


def test_t37_updateticket_applies_changes_and_reports_validation_failures(suite_results):
    _assert_scenario(suite_results, "T37", 'updateTicket applies changes and reports validation failures')


def test_t38_updating_a_missing_record_yields_a_not_found_error_in_the_result(suite_results):
    _assert_scenario(suite_results, "T38", 'updating a missing record yields a not_found error in the result')


def test_t39_destroying_a_ticket_removes_it_and_ticketorfail_then_errors_at_the_top_level(suite_results):
    _assert_scenario(suite_results, "T39", 'destroying a ticket removes it and ticketOrFail then errors at the top level')


def test_t40_archiveproject_is_forbidden_without_an_admin_actor(suite_results):
    _assert_scenario(suite_results, "T40", 'archiveProject is forbidden without an admin actor')


def test_t41_the_generic_action_mutation_returns_its_string_result(suite_results):
    _assert_scenario(suite_results, "T41", 'the generic action mutation returns its string result')


def test_t42_the_custom_exception_surfaces_through_the_ashgraphql_error_protocol(suite_results):
    _assert_scenario(suite_results, "T42", 'the custom exception surfaces through the AshGraphql.Error protocol')


def test_t43_raised_errors_are_shown_because_the_domain_enables_them(suite_results):
    _assert_scenario(suite_results, "T43", 'raised errors are shown because the domain enables them')


def test_t44_the_hand_written_ticketbyreference_query_loads_requested_fields(suite_results):
    _assert_scenario(suite_results, "T44", 'the hand written ticketByReference query loads requested fields')
