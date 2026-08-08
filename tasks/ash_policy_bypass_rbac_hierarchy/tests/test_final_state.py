"""Final-state verification for the ash_policy_bypass_rbac_hierarchy task.

The whole Ash authorization contract is exercised by a single self-contained ExUnit
suite that is written to /tmp at verification time and executed with `mix run`
inside the executor's project. The suite emits one machine-readable line per
scenario, which is parsed here so that every scenario is reported as its own
pytest case.
"""

import base64
import os
import re
import subprocess

import pytest

PROJECT_DIR = "/home/user/orgguard"
SUITE_PATH = "/tmp/harbor_rbac_suite.exs"
RESULT_RE = re.compile(r"^@@HARBOR@@(?:test )?(T\d+)[^@]*@@(passed|failed)@@(.*)$")

SUITE_SOURCE = r"""
defmodule HarborFormatter do
  @moduledoc false
  use GenServer

  def init(_opts), do: {:ok, %{}}

  def handle_cast({:test_finished, test}, state) do
    {status, detail} =
      case test.state do
        nil -> {"passed", ""}
        {:failed, failures} -> {"failed", format(test, failures)}
        {:invalid, _} -> {"failed", "test was invalid (setup failed)"}
        {:excluded, _} -> {"passed", ""}
        {:skipped, _} -> {"passed", ""}
      end

    IO.puts(
      "@@HARBOR@@" <>
        to_string(test.name) <> "@@" <> status <> "@@" <> Base.encode64(detail)
    )

    {:noreply, state}
  end

  def handle_cast(_event, state), do: {:noreply, state}

  defp format(test, failures) do
    ExUnit.Formatter.format_test_failure(test, failures, 1, 120, fn _, msg -> msg end)
  rescue
    e -> "could not format failure: " <> Exception.message(e)
  end
end

ExUnit.start(
  autorun: false,
  formatters: [HarborFormatter],
  seed: 0,
  colors: [enabled: false],
  max_failures: :infinity,
  timeout: 120_000
)

domain = Module.concat(["OrgGuard", "Access"])
document = Module.concat(["OrgGuard", "Access", "Document"])
user_res = Module.concat(["OrgGuard", "Access", "User"])
org_unit_res = Module.concat(["OrgGuard", "Access", "OrgUnit"])
role_res = Module.concat(["OrgGuard", "Access", "RoleAssignment"])

seed = fn ->
  mk_unit = fn code, name, parent_id ->
    apply(domain, :create_org_unit!, [
      %{code: code, name: name, parent_id: parent_id},
      [authorize?: false]
    ])
  end

  acme = mk_unit.("acme", "Acme", nil)
  eng = mk_unit.("eng", "Engineering", acme.id)
  platform = mk_unit.("eng-platform", "Platform", eng.id)
  db = mk_unit.("eng-platform-db", "Database", platform.id)
  web = mk_unit.("eng-web", "Web", eng.id)
  fin = mk_unit.("fin", "Finance", acme.id)
  payroll = mk_unit.("fin-payroll", "Payroll", fin.id)

  units = %{
    "acme" => acme,
    "eng" => eng,
    "eng-platform" => platform,
    "eng-platform-db" => db,
    "eng-web" => web,
    "fin" => fin,
    "fin-payroll" => payroll
  }

  mk_user = fn email, status, global_role ->
    apply(domain, :create_user!, [
      %{email: email, status: status, global_role: global_role},
      [authorize?: false]
    ])
  end

  assign = fn user, unit, role, effect ->
    apply(domain, :create_role_assignment!, [
      %{user_id: user.id, org_unit_id: unit.id, role: role, effect: effect},
      [authorize?: false]
    ])
  end

  root_admin = mk_user.("root_admin@orgguard.test", :active, :member)
  assign.(root_admin, acme, :unit_admin, :grant)

  eng_admin = mk_user.("eng_admin@orgguard.test", :active, :member)
  assign.(eng_admin, eng, :unit_admin, :grant)

  eng_viewer = mk_user.("eng_viewer@orgguard.test", :active, :member)
  assign.(eng_viewer, eng, :viewer, :grant)

  web_editor = mk_user.("web_editor@orgguard.test", :active, :member)
  assign.(web_editor, web, :editor, :grant)

  deny_viewer = mk_user.("deny_viewer@orgguard.test", :active, :member)
  assign.(deny_viewer, eng, :viewer, :grant)
  assign.(deny_viewer, platform, :viewer, :deny)

  regrant_viewer = mk_user.("regrant_viewer@orgguard.test", :active, :member)
  assign.(regrant_viewer, acme, :viewer, :grant)
  assign.(regrant_viewer, eng, :viewer, :deny)
  assign.(regrant_viewer, platform, :viewer, :grant)

  fin_auditor = mk_user.("fin_auditor@orgguard.test", :active, :member)
  assign.(fin_auditor, fin, :auditor, :grant)

  platform_pair = mk_user.("platform_pair@orgguard.test", :active, :member)
  assign.(platform_pair, platform, :editor, :grant)
  assign.(platform_pair, platform, :auditor, :grant)

  no_roles = mk_user.("no_roles@orgguard.test", :active, :member)

  suspended_admin = mk_user.("suspended_admin@orgguard.test", :suspended, :member)
  assign.(suspended_admin, acme, :unit_admin, :grant)

  suspended_none = mk_user.("suspended_none@orgguard.test", :suspended, :member)
  breakglass = mk_user.("breakglass@orgguard.test", :active, :break_glass)
  breakglass_susp = mk_user.("breakglass_susp@orgguard.test", :suspended, :break_glass)

  users = %{
    "root_admin" => root_admin,
    "eng_admin" => eng_admin,
    "eng_viewer" => eng_viewer,
    "web_editor" => web_editor,
    "deny_viewer" => deny_viewer,
    "regrant_viewer" => regrant_viewer,
    "fin_auditor" => fin_auditor,
    "platform_pair" => platform_pair,
    "no_roles" => no_roles,
    "suspended_admin" => suspended_admin,
    "suspended_none" => suspended_none,
    "breakglass" => breakglass,
    "breakglass_susp" => breakglass_susp
  }

  mk_doc = fn title, unit, budget ->
    apply(domain, :create_document!, [
      %{title: title, budget_cents: budget, org_unit_id: unit.id},
      [authorize?: false]
    ])
  end

  docs =
    Map.new(
      [
        {"F-acme", acme, 1_000_000},
        {"F-eng", eng, 200_000},
        {"F-platform", platform, 30_000},
        {"F-db", db, 4_000},
        {"F-web", web, 5_000},
        {"F-fin", fin, 600_000},
        {"F-payroll", payroll, 70_000}
      ],
      fn {title, unit, budget} -> {title, mk_doc.(title, unit, budget)} end
    )

  %{units: units, users: users, docs: docs}
end

fixture =
  try do
    seed.()
  rescue
    e -> {:seed_failed, Exception.format(:error, e, __STACKTRACE__)}
  catch
    kind, reason -> {:seed_failed, Exception.format(kind, reason, __STACKTRACE__)}
  end

:persistent_term.put(:harbor_fixture, fixture)

defmodule OrgGuardRbacTest do
  use ExUnit.Case, async: false

  @domain Module.concat(["OrgGuard", "Access"])
  @document Module.concat(["OrgGuard", "Access", "Document"])
  @user Module.concat(["OrgGuard", "Access", "User"])
  @org_unit Module.concat(["OrgGuard", "Access", "OrgUnit"])
  @role_assignment Module.concat(["OrgGuard", "Access", "RoleAssignment"])

  @fixture_titles ~w(F-acme F-eng F-platform F-db F-web F-fin F-payroll)

  defp fx do
    case :persistent_term.get(:harbor_fixture, nil) do
      {:seed_failed, detail} -> flunk("fixture seeding failed:\n" <> detail)
      nil -> flunk("fixture was never seeded")
      fixture -> fixture
    end
  end

  defp user(name), do: Map.fetch!(fx().users, name)
  defp unit(code), do: Map.fetch!(fx().units, code)
  defp doc(title), do: Map.fetch!(fx().docs, title)

  defp call(fun, args), do: apply(@domain, fun, args)

  defp list(actor), do: call(:list_documents, [[actor: actor]])

  defp fixture_titles(actor) do
    case list(actor) do
      {:ok, docs} ->
        docs
        |> Enum.map(& &1.title)
        |> Enum.filter(&(&1 in @fixture_titles))
        |> Enum.sort()

      other ->
        flunk("expected a successful list read, got: #{inspect(other)}")
    end
  end

  defp fixture_budgets(actor) do
    case list(actor) do
      {:ok, docs} ->
        docs
        |> Enum.filter(&(&1.title in @fixture_titles))
        |> Map.new(&{&1.title, &1.budget_cents})

      other ->
        flunk("expected a successful list read, got: #{inspect(other)}")
    end
  end

  defp error_class({:error, %{class: class}}), do: class
  defp error_class(other), do: {:no_error, other}

  defp forbidden?(result), do: error_class(result) == :forbidden

  defp has_error?({:error, %{errors: errors}}, mod),
    do: Enum.any?(errors, &(&1.__struct__ == mod))

  defp has_error?(_, _), do: false

  defp not_found?(result), do: has_error?(result, Ash.Error.Query.NotFound)

  defp mk_doc(unit_code, budget \\ 100) do
    call(:create_document!, [
      %{
        title: "M-#{System.unique_integer([:positive])}",
        budget_cents: budget,
        org_unit_id: unit(unit_code).id
      },
      [authorize?: false]
    ])
  end

  defp reload(record), do: Ash.get!(@document, record.id, authorize?: false)

  defp reload_or_nil(record) do
    case Ash.get(@document, record.id, authorize?: false) do
      {:ok, rec} -> rec
      _ -> nil
    end
  end

  defp check_modules(resource) do
    policies = Ash.Policy.Info.policies(resource) ++ Ash.Policy.Info.field_policies(resource)

    policies
    |> Enum.flat_map(fn policy ->
      conditions = policy.condition || []
      Enum.map(conditions, fn {mod, _opts} -> mod end) ++
        Enum.map(policy.policies, & &1.check_module)
    end)
    |> Enum.uniq()
  end

  defp custom_check_modules(resource) do
    resource
    |> check_modules()
    |> Enum.reject(&String.starts_with?(inspect(&1), "Ash."))
    |> Enum.filter(&Code.ensure_loaded?/1)
  end

  defp check_type?(mod, type) do
    function_exported?(mod, :type, 0) and mod.type() == type
  end

  # --------------------------------------------------------------- structure

  test "T01 Document is authorized by Ash.Policy.Authorizer and the other resources are not" do
    assert Ash.Policy.Authorizer in Ash.Resource.Info.authorizers(@document),
           "OrgGuard.Access.Document must use Ash.Policy.Authorizer"

    for resource <- [@user, @org_unit, @role_assignment] do
      assert Ash.Resource.Info.authorizers(resource) == [],
             "#{inspect(resource)} must not declare an authorizer"
    end
  end

  test "T02 Document policies contain at least one bypass policy" do
    policies = Ash.Policy.Info.policies(@document)
    assert policies != [], "OrgGuard.Access.Document declares no policies"

    assert Enum.any?(policies, &(&1.bypass? == true)),
           "expected at least one bypass policy on OrgGuard.Access.Document"
  end

  test "T03 a custom filter check module is used by Document policies" do
    mods = custom_check_modules(@document)

    assert Enum.any?(mods, &check_type?(&1, :filter)),
           "expected a self-defined filter check module among #{inspect(mods)}"
  end

  test "T04 a custom simple check module is used by Document policies" do
    mods = custom_check_modules(@document)

    assert Enum.any?(mods, &check_type?(&1, :simple)),
           "expected a self-defined simple check module among #{inspect(mods)}"
  end

  test "T05 budget_cents is governed by at least one field policy" do
    assert Ash.Policy.Info.field_policies_for_field(@document, :budget_cents) != [],
           "expected at least one field policy covering :budget_cents"
  end

  test "T06 relocate is a generic action with the required uuid arguments" do
    action = Ash.Resource.Info.action(@document, :relocate)
    assert action, "OrgGuard.Access.Document has no :relocate action"
    assert action.type == :action, "the :relocate action must be a generic action"

    args = Map.new(action.arguments, &{&1.name, &1})

    for name <- [:document_id, :target_org_unit_id] do
      argument = Map.get(args, name)
      assert argument, "the :relocate action is missing the #{inspect(name)} argument"
      assert argument.type == Ash.Type.UUID, "#{inspect(name)} must be a :uuid argument"
      refute argument.allow_nil?, "#{inspect(name)} must be required"
    end
  end

  test "T07 the seeded fixture is readable without authorization" do
    docs = Ash.read!(@document, authorize?: false)
    titles = docs |> Enum.map(& &1.title) |> Enum.filter(&(&1 in @fixture_titles)) |> Enum.sort()
    assert titles == Enum.sort(@fixture_titles)

    budgets =
      docs
      |> Enum.filter(&(&1.title in @fixture_titles))
      |> Map.new(&{&1.title, &1.budget_cents})

    assert budgets["F-acme"] == 1_000_000
    assert budgets["F-payroll"] == 70_000
    assert Enum.all?(Map.values(budgets), &is_integer/1)
  end

  # -------------------------------------------------------------- read scope

  test "T08 a root grant is inherited by the whole tree" do
    assert fixture_titles(user("root_admin")) == Enum.sort(@fixture_titles)
  end

  test "T09 a subtree grant reaches three levels down" do
    assert fixture_titles(user("eng_viewer")) == Enum.sort(~w(F-eng F-platform F-db F-web))
  end

  test "T10 a deny at a descendant cuts off the inherited grant for that subtree" do
    assert fixture_titles(user("deny_viewer")) == Enum.sort(~w(F-eng F-web))
  end

  test "T11 a grant below a deny re-establishes access" do
    assert fixture_titles(user("regrant_viewer")) ==
             Enum.sort(~w(F-acme F-fin F-payroll F-platform F-db))
  end

  test "T12 an actor with no role assignments sees an empty list, not an error" do
    assert {:ok, docs} = list(user("no_roles"))
    assert Enum.filter(docs, &(&1.title in @fixture_titles)) == []
  end

  test "T13 a nil actor sees an empty list, not an error" do
    assert {:ok, docs} = list(nil)
    assert Enum.filter(docs, &(&1.title in @fixture_titles)) == []
  end

  test "T14 a suspended actor holding roles is forbidden from listing" do
    result = list(user("suspended_admin"))
    assert forbidden?(result), "expected Ash.Error.Forbidden, got: #{inspect(result)}"
  end

  test "T15 a suspended actor without roles is forbidden from listing" do
    result = list(user("suspended_none"))
    assert forbidden?(result), "expected Ash.Error.Forbidden, got: #{inspect(result)}"
  end

  test "T16 a break-glass actor sees every document" do
    assert fixture_titles(user("breakglass")) == Enum.sort(@fixture_titles)
  end

  test "T17 break-glass takes precedence over suspension" do
    assert fixture_titles(user("breakglass_susp")) == Enum.sort(@fixture_titles)
  end

  # ------------------------------------------------------------ direct fetch

  test "T18 fetching a filtered-out document by id is not-found, not forbidden" do
    actor = user("deny_viewer")

    for title <- ~w(F-platform F-db) do
      result = call(:get_document, [doc(title).id, [actor: actor]])
      assert not_found?(result), "expected NotFound for #{title}, got: #{inspect(result)}"
      refute forbidden?(result), "expected NotFound (not Forbidden) for #{title}"
    end
  end

  test "T19 fetching a permitted document by id succeeds" do
    assert {:ok, fetched} = call(:get_document, [doc("F-eng").id, [actor: user("eng_viewer")]])
    assert fetched.id == doc("F-eng").id
  end

  test "T20 fetching by id with a nil actor is not-found" do
    result = call(:get_document, [doc("F-fin").id, [actor: nil]])
    assert not_found?(result), "expected NotFound, got: #{inspect(result)}"
  end

  test "T21 fetching by id as a suspended actor is forbidden" do
    result = call(:get_document, [doc("F-acme").id, [actor: user("suspended_admin")]])
    assert forbidden?(result), "expected Ash.Error.Forbidden, got: #{inspect(result)}"
    refute not_found?(result), "a suspended actor must get Forbidden, not NotFound"
  end

  # ---------------------------------------------------------------- updates

  test "T22 an editor may update the title of a document in its unit" do
    record = mk_doc("eng-web")
    assert {:ok, _} = call(:update_document, [record, %{title: "M-renamed"}, [actor: user("web_editor")]])
    assert reload(record).title == "M-renamed"
  end

  test "T23 a viewer may not update" do
    record = mk_doc("eng-web")
    result = call(:update_document, [record, %{title: "nope"}, [actor: user("eng_viewer")]])
    assert forbidden?(result), "expected Ash.Error.Forbidden, got: #{inspect(result)}"
    assert reload(record).title == record.title
  end

  test "T24 write without view_budget cannot change budget_cents" do
    record = mk_doc("eng-web", 777)
    result = call(:update_document, [record, %{budget_cents: 999}, [actor: user("web_editor")]])
    assert forbidden?(result), "expected Ash.Error.Forbidden, got: #{inspect(result)}"
    assert reload(record).budget_cents == 777
  end

  test "T25 write plus view_budget may change budget_cents" do
    record = mk_doc("eng-platform", 1)
    assert {:ok, _} = call(:update_document, [record, %{budget_cents: 12_345}, [actor: user("platform_pair")]])
    assert reload(record).budget_cents == 12_345
  end

  test "T26 unit_admin inherits the right to change budget_cents deep in the tree" do
    record = mk_doc("eng-platform-db", 2)
    assert {:ok, _} = call(:update_document, [record, %{budget_cents: 4_242}, [actor: user("root_admin")]])
    assert reload(record).budget_cents == 4_242
  end

  test "T27 break-glass may update anything" do
    record = mk_doc("fin-payroll", 3)

    assert {:ok, _} =
             call(:update_document, [
               record,
               %{title: "M-bg", budget_cents: 5_005},
               [actor: user("breakglass")]
             ])

    updated = reload(record)
    assert updated.title == "M-bg"
    assert updated.budget_cents == 5_005
  end

  # --------------------------------------------------------- field policies

  test "T28 an auditor sees the budgets in its subtree" do
    budgets = fixture_budgets(user("fin_auditor"))
    assert Map.keys(budgets) |> Enum.sort() == Enum.sort(~w(F-fin F-payroll))
    assert budgets["F-fin"] == 600_000
    assert budgets["F-payroll"] == 70_000
  end

  test "T29 a reader without view_budget gets the forbidden-field marker" do
    budgets = fixture_budgets(user("eng_viewer"))

    assert match?(%Ash.ForbiddenField{field: :budget_cents, type: :attribute}, budgets["F-eng"]),
           "expected %Ash.ForbiddenField{field: :budget_cents, type: :attribute}, got: #{inspect(budgets["F-eng"])}"

    assert Enum.all?(Map.values(budgets), &match?(%Ash.ForbiddenField{}, &1))

    titles = fixture_titles(user("eng_viewer"))
    assert "F-eng" in titles, "other attributes must stay visible"
  end

  test "T30 break-glass sees every budget" do
    budgets = fixture_budgets(user("breakglass"))
    assert map_size(budgets) == 7
    assert Enum.all?(Map.values(budgets), &is_integer/1), "got: #{inspect(budgets)}"
  end

  test "T31 view_budget is inherited like every other capability" do
    root = fixture_budgets(user("root_admin"))
    assert map_size(root) == 7
    assert Enum.all?(Map.values(root), &is_integer/1), "got: #{inspect(root)}"

    pair = fixture_budgets(user("platform_pair"))
    assert is_integer(pair["F-db"]), "got: #{inspect(pair["F-db"])}"

    viewer = fixture_budgets(user("eng_viewer"))
    refute is_integer(viewer["F-db"])
  end

  # --------------------------------------------------------------- destroys

  test "T32 destroying without the delete capability is forbidden" do
    record = mk_doc("eng-web")

    for actor_name <- ~w(web_editor no_roles) do
      result = call(:destroy_document, [record, [actor: user(actor_name)]])
      assert forbidden?(result), "expected Forbidden for #{actor_name}, got: #{inspect(result)}"
    end

    assert reload_or_nil(record), "the document must still exist"
  end

  test "T33 unit_admin and break-glass may destroy" do
    first = mk_doc("eng-web")
    assert :ok == call(:destroy_document, [first, [actor: user("root_admin")]])
    refute reload_or_nil(first), "the document should be gone"

    second = mk_doc("eng-web")
    assert :ok == call(:destroy_document, [second, [actor: user("breakglass")]])
    refute reload_or_nil(second), "the document should be gone"
  end

  # ---------------------------------------------------------------- creates

  test "T34 creating with the write capability at the target unit succeeds" do
    assert {:ok, created} =
             call(:create_document, [
               %{title: "M-created", budget_cents: 11, org_unit_id: unit("eng-web").id},
               [actor: user("web_editor")]
             ])

    assert reload(created).org_unit_id == unit("eng-web").id
  end

  test "T35 creating without the write capability is forbidden" do
    viewer_result =
      call(:create_document, [
        %{title: "M-nope", budget_cents: 1, org_unit_id: unit("eng-platform").id},
        [actor: user("eng_viewer")]
      ])

    assert forbidden?(viewer_result), "expected Forbidden, got: #{inspect(viewer_result)}"

    nil_result =
      call(:create_document, [
        %{title: "M-nope", budget_cents: 1, org_unit_id: unit("eng-platform").id},
        [actor: nil]
      ])

    assert forbidden?(nil_result), "expected Forbidden, got: #{inspect(nil_result)}"
  end

  # ------------------------------------------------------------- relocation

  test "T36 relocation succeeds when the actor may relocate at both ends" do
    record = mk_doc("eng-web")
    target = unit("fin-payroll").id

    assert {:ok, returned} =
             call(:relocate_document, [record.id, target, [actor: user("root_admin")]])

    assert returned.org_unit_id == target
    assert reload(record).org_unit_id == target
  end

  test "T37 relocation is forbidden without the relocate capability" do
    record = mk_doc("eng-web")
    source = record.org_unit_id

    result =
      call(:relocate_document, [record.id, unit("eng-platform").id, [actor: user("web_editor")]])

    assert forbidden?(result), "expected Ash.Error.Forbidden, got: #{inspect(result)}"
    assert reload(record).org_unit_id == source, "the document must not move"
  end

  test "T38 relocation is forbidden when only the source unit is in scope" do
    record = mk_doc("eng-web")
    source = record.org_unit_id

    result = call(:relocate_document, [record.id, unit("fin").id, [actor: user("eng_admin")]])
    assert forbidden?(result), "expected Ash.Error.Forbidden, got: #{inspect(result)}"
    assert reload(record).org_unit_id == source, "the document must not move"

    assert {:ok, _} =
             call(:relocate_document, [
               record.id,
               unit("eng-platform-db").id,
               [actor: user("eng_admin")]
             ])

    assert reload(record).org_unit_id == unit("eng-platform-db").id
  end

  # -------------------------------------------------------- can? matrix

  test "T39 can_update_document? agrees with the update contract" do
    record = mk_doc("eng-web")

    assert call(:can_update_document?, [user("web_editor"), record]) == true
    assert call(:can_update_document?, [user("breakglass"), record]) == true
    assert call(:can_update_document?, [user("eng_viewer"), record]) == false
    assert call(:can_update_document?, [user("suspended_admin"), record]) == false
    assert call(:can_update_document?, [nil, record]) == false
  end

  test "T40 can_destroy_document? and Ash.can?/3 agree with the destroy contract" do
    record = doc("F-web")

    assert call(:can_destroy_document?, [user("root_admin"), record]) == true
    assert call(:can_destroy_document?, [user("web_editor"), record]) == false
    assert call(:can_destroy_document?, [nil, record]) == false

    assert Ash.can?({@document, :destroy, %{}}, user("root_admin"), data: record) == true
    assert Ash.can?({@document, :destroy, %{}}, user("web_editor"), data: record) == false
  end

  test "T41 can_create_document? agrees with the create contract" do
    editor = user("web_editor")

    assert call(:can_create_document?, [editor, %{org_unit_id: unit("eng-web").id}]) == true
    assert call(:can_create_document?, [editor, %{org_unit_id: unit("fin").id}]) == false
    assert call(:can_create_document?, [nil, %{org_unit_id: unit("eng-web").id}]) == false
  end

  test "T42 can_relocate_document? agrees with the relocation contract" do
    record = mk_doc("eng-web")

    assert call(:can_relocate_document?, [user("root_admin"), record.id, unit("fin").id]) == true
    assert call(:can_relocate_document?, [user("eng_admin"), record.id, unit("fin").id]) == false

    assert call(:can_relocate_document?, [
             user("eng_admin"),
             record.id,
             unit("eng-platform").id
           ]) == true

    assert call(:can_relocate_document?, [nil, record.id, unit("fin").id]) == false
  end
end

_ = {document, user_res, org_unit_res, role_res}

ExUnit.run()
"""


def _run_suite() -> dict[str, tuple[str, str]]:
    with open(SUITE_PATH, "w", encoding="utf-8") as handle:
        handle.write(SUITE_SOURCE.lstrip("\n"))

    env = dict(os.environ)
    env["MIX_ENV"] = "dev"
    env["HEX_OFFLINE"] = "1"

    proc = subprocess.run(
        ["mix", "run", SUITE_PATH],
        cwd=PROJECT_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=1800,
        check=False,
    )

    output = proc.stdout + "\n" + proc.stderr
    results: dict[str, tuple[str, str]] = {}

    for line in output.splitlines():
        match = RESULT_RE.match(line.strip())
        if match is None:
            continue
        scenario, status, encoded = match.groups()
        try:
            detail = base64.b64decode(encoded).decode("utf-8", errors="replace")
        except Exception:  # pragma: no cover - defensive
            detail = encoded
        results[scenario] = (status, detail)

    if not results:
        tail = "\n".join(output.splitlines()[-80:])
        results["__error__"] = (
            "failed",
            "The ExUnit contract suite produced no results "
            f"(exit code {proc.returncode}). Output tail:\n{tail}",
        )

    return results


@pytest.fixture(scope="session")
def suite_results() -> dict[str, tuple[str, str]]:
    return _run_suite()


def _check(results: dict[str, tuple[str, str]], scenario: str) -> None:
    if "__error__" in results:
        pytest.fail(results["__error__"][1])

    assert scenario in results, (
        f"Scenario {scenario} never ran. Scenarios reported: {sorted(results)}"
    )
    status, detail = results[scenario]
    assert status == "passed", f"Scenario {scenario} failed:\n{detail}"


def test_t01_document_is_authorized_by_policy_authorizer(suite_results):
    _check(suite_results, "T01")


def test_t02_policies_contain_a_bypass(suite_results):
    _check(suite_results, "T02")


def test_t03_a_custom_filter_check_is_used(suite_results):
    _check(suite_results, "T03")


def test_t04_a_custom_simple_check_is_used(suite_results):
    _check(suite_results, "T04")


def test_t05_budget_cents_has_a_field_policy(suite_results):
    _check(suite_results, "T05")


def test_t06_relocate_is_a_generic_action_with_uuid_arguments(suite_results):
    _check(suite_results, "T06")


def test_t07_seeded_fixture_is_readable_without_authorization(suite_results):
    _check(suite_results, "T07")


def test_t08_root_grant_is_inherited_by_the_whole_tree(suite_results):
    _check(suite_results, "T08")


def test_t09_subtree_grant_reaches_three_levels_down(suite_results):
    _check(suite_results, "T09")


def test_t10_deny_at_a_descendant_cuts_off_the_inherited_grant(suite_results):
    _check(suite_results, "T10")


def test_t11_grant_below_a_deny_re_establishes_access(suite_results):
    _check(suite_results, "T11")


def test_t12_actor_without_roles_gets_an_empty_list(suite_results):
    _check(suite_results, "T12")


def test_t13_nil_actor_gets_an_empty_list(suite_results):
    _check(suite_results, "T13")


def test_t14_suspended_actor_with_roles_is_forbidden(suite_results):
    _check(suite_results, "T14")


def test_t15_suspended_actor_without_roles_is_forbidden(suite_results):
    _check(suite_results, "T15")


def test_t16_break_glass_actor_sees_every_document(suite_results):
    _check(suite_results, "T16")


def test_t17_break_glass_takes_precedence_over_suspension(suite_results):
    _check(suite_results, "T17")


def test_t18_filtered_out_fetch_by_id_is_not_found(suite_results):
    _check(suite_results, "T18")


def test_t19_permitted_fetch_by_id_succeeds(suite_results):
    _check(suite_results, "T19")


def test_t20_nil_actor_fetch_by_id_is_not_found(suite_results):
    _check(suite_results, "T20")


def test_t21_suspended_actor_fetch_by_id_is_forbidden(suite_results):
    _check(suite_results, "T21")


def test_t22_editor_may_update_the_title(suite_results):
    _check(suite_results, "T22")


def test_t23_viewer_may_not_update(suite_results):
    _check(suite_results, "T23")


def test_t24_write_without_view_budget_cannot_change_the_budget(suite_results):
    _check(suite_results, "T24")


def test_t25_write_plus_view_budget_may_change_the_budget(suite_results):
    _check(suite_results, "T25")


def test_t26_unit_admin_inherits_the_right_to_change_the_budget(suite_results):
    _check(suite_results, "T26")


def test_t27_break_glass_may_update_anything(suite_results):
    _check(suite_results, "T27")


def test_t28_auditor_sees_the_budgets_in_its_subtree(suite_results):
    _check(suite_results, "T28")


def test_t29_reader_without_view_budget_gets_the_forbidden_field_marker(suite_results):
    _check(suite_results, "T29")


def test_t30_break_glass_sees_every_budget(suite_results):
    _check(suite_results, "T30")


def test_t31_view_budget_is_inherited(suite_results):
    _check(suite_results, "T31")


def test_t32_destroy_without_the_delete_capability_is_forbidden(suite_results):
    _check(suite_results, "T32")


def test_t33_unit_admin_and_break_glass_may_destroy(suite_results):
    _check(suite_results, "T33")


def test_t34_create_with_the_write_capability_succeeds(suite_results):
    _check(suite_results, "T34")


def test_t35_create_without_the_write_capability_is_forbidden(suite_results):
    _check(suite_results, "T35")


def test_t36_relocation_succeeds_when_both_ends_are_in_scope(suite_results):
    _check(suite_results, "T36")


def test_t37_relocation_without_the_capability_is_forbidden(suite_results):
    _check(suite_results, "T37")


def test_t38_relocation_with_only_the_source_in_scope_is_forbidden(suite_results):
    _check(suite_results, "T38")


def test_t39_can_update_document_matches_the_update_contract(suite_results):
    _check(suite_results, "T39")


def test_t40_can_destroy_document_matches_the_destroy_contract(suite_results):
    _check(suite_results, "T40")


def test_t41_can_create_document_matches_the_create_contract(suite_results):
    _check(suite_results, "T41")


def test_t42_can_relocate_document_matches_the_relocation_contract(suite_results):
    _check(suite_results, "T42")
