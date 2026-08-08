"""Final-state verification for the ash_soft_delete_archive_cascade task.

The Ash/Elixir behaviour under test is exercised by a self-contained ExUnit
suite that is executed against the executor's real project with ``mix run``.
A custom ExUnit formatter emits one machine-readable ``HARBOR_RESULT`` JSON line
per scenario, and every scenario is surfaced here as its own pytest case.
"""

import json
import os
import subprocess

import pytest

PROJECT_DIR = "/home/user/forum"
SCRIPT_PATH = "/tmp/harbor_archive_contract.exs"
RESULT_PREFIX = "HARBOR_RESULT "

ARCHIVE_CONTRACT_EXS = r"""
defmodule Harbor.Formatter do
  @moduledoc false
  use GenServer

  @impl true
  def init(_opts), do: {:ok, %{}}

  @impl true
  def handle_cast({:test_finished, test}, state) do
    {status, message} =
      case test.state do
        nil ->
          {"pass", ""}

        {:excluded, reason} ->
          {"skip", to_string(reason)}

        {:skipped, reason} ->
          {"skip", to_string(reason)}

        {:failed, failures} ->
          {"fail", safe_failure(test, failures)}

        {:invalid, _module} ->
          {"fail", "test module setup failed"}
      end

    name =
      test.name
      |> Atom.to_string()
      |> String.replace_prefix("test ", "")

    IO.puts(
      "HARBOR_RESULT " <>
        Jason.encode!(%{"name" => name, "status" => status, "message" => message})
    )

    {:noreply, state}
  end

  def handle_cast(_event, state), do: {:noreply, state}

  defp safe_failure(test, failures) do
    ExUnit.Formatter.format_test_failure(test, failures, 1, 400, fn _kind, msg -> msg end)
  rescue
    _ -> inspect(failures, limit: 20, printable_limit: 400)
  end
end

ExUnit.start(
  autorun: false,
  formatters: [Harbor.Formatter],
  max_failures: :infinity,
  seed: 0,
  colors: [enabled: false],
  timeout: 120_000
)

defmodule H do
  @moduledoc false
  require Ash.Query

  def post(title \\ "P") do
    Forum.Content.Post
    |> Ash.Changeset.for_create(:create, %{title: title}, authorize?: false)
    |> Ash.create!(authorize?: false)
  end

  def comment(post, body) do
    Forum.Content.Comment
    |> Ash.Changeset.for_create(:create, %{body: body, post_id: post.id}, authorize?: false)
    |> Ash.create!(authorize?: false)
  end

  def reaction(comment, emoji) do
    Forum.Content.Reaction
    |> Ash.Changeset.for_create(:create, %{emoji: emoji, comment_id: comment.id},
      authorize?: false
    )
    |> Ash.create!(authorize?: false)
  end

  def tree do
    p = post("P")
    c1 = comment(p, "c1")
    c2 = comment(p, "c2")
    r1 = reaction(c1, "r1")
    r2 = reaction(c2, "r2")
    %{p: p, c1: c1, c2: c2, r1: r1, r2: r2}
  end

  def read(resource, action \\ :read) do
    resource
    |> Ash.Query.for_read(action, %{})
    |> Ash.read!(authorize?: false)
  end

  def reload(%module{} = record) do
    module
    |> Ash.Query.for_read(:with_archived, %{})
    |> Ash.Query.filter(id == ^record.id)
    |> Ash.read_one!(authorize?: false)
  end

  def reload_all(records), do: Enum.map(records, &reload/1)

  def archive!(record) do
    record
    |> Ash.Changeset.for_destroy(:archive, %{}, authorize?: false)
    |> Ash.destroy(authorize?: false)
    |> case do
      :ok -> :ok
      {:ok, _} -> :ok
      {:ok, _, _} -> :ok
      other -> raise "archive failed: #{inspect(other)}"
    end
  end

  def restore!(record) do
    record
    |> Ash.Changeset.for_update(:restore, %{}, authorize?: false)
    |> Ash.update(authorize?: false)
    |> case do
      {:ok, updated} -> updated
      other -> raise "restore failed: #{inspect(other)}"
    end
  end

  def purge(record) do
    record
    |> Ash.Changeset.for_destroy(:purge, %{}, authorize?: false)
    |> Ash.destroy(authorize?: false)
  end

  def purge!(record) do
    case purge(record) do
      :ok -> :ok
      {:ok, _} -> :ok
      other -> raise "purge failed: #{inspect(other)}"
    end
  end

  def archived?(record), do: not is_nil(record.archived_at)

  def marks(record), do: {record.archived_at, record.archive_batch_id}

  def titles(records), do: records |> Enum.map(& &1.title) |> Enum.sort()
  def bodies(records), do: records |> Enum.map(& &1.body) |> Enum.sort()
  def emojis(records), do: records |> Enum.map(& &1.emoji) |> Enum.sort()

  def preparation_modules(resource, action_name) do
    action = Ash.Resource.Info.action(resource, action_name)

    (Ash.Resource.Info.preparations(resource) ++ (Map.get(action, :preparations) || []))
    |> Enum.map(&Map.get(&1, :preparation))
    |> Enum.map(&module_of/1)
    |> Enum.reject(&is_nil/1)
  end

  def change_modules(resource, action_name) do
    action = Ash.Resource.Info.action(resource, action_name)

    (Ash.Resource.Info.changes(resource, action.type) ++ (Map.get(action, :changes) || []))
    |> Enum.map(&Map.get(&1, :change))
    |> Enum.map(&module_of/1)
    |> Enum.reject(&is_nil/1)
  end

  defp module_of({module, _opts}) when is_atom(module), do: module
  defp module_of(module) when is_atom(module), do: module
  defp module_of(_), do: nil

  def flat_errors(%{errors: errors}) when is_list(errors), do: errors
  def flat_errors(error), do: [error]
end

defmodule ArchiveContractTest do
  use ExUnit.Case, async: false

  require Ash.Query

  @resources [Forum.Content.Post, Forum.Content.Comment, Forum.Content.Reaction]

  test "s01_structure_resources_actions_and_attributes" do
    registered = Ash.Domain.Info.resources(Forum.Content)

    for resource <- @resources do
      assert resource in registered,
             "#{inspect(resource)} is not registered in the Forum.Content domain"
    end

    for resource <- @resources do
      assert Ash.Resource.Info.data_layer(resource) == Ash.DataLayer.Ets,
             "#{inspect(resource)} must use Ash.DataLayer.Ets"

      assert Ash.DataLayer.Ets.Info.private?(resource),
             "#{inspect(resource)} must configure its ETS data layer with private? true"

      assert Ash.Policy.Authorizer in Ash.Resource.Info.authorizers(resource),
             "#{inspect(resource)} must use Ash.Policy.Authorizer"

      assert Ash.Resource.Info.attribute(resource, :archived_at).type ==
               Ash.Type.UtcDatetimeUsec,
             "#{inspect(resource)}.archived_at must be a :utc_datetime_usec attribute"

      assert Ash.Resource.Info.attribute(resource, :archive_batch_id).type == Ash.Type.UUID,
             "#{inspect(resource)}.archive_batch_id must be a :uuid attribute"

      for {name, type} <- [
            {:create, :create},
            {:read, :read},
            {:archived, :read},
            {:with_archived, :read},
            {:archive, :destroy},
            {:restore, :update},
            {:purge, :destroy}
          ] do
        action = Ash.Resource.Info.action(resource, name)
        assert action, "#{inspect(resource)} is missing the #{inspect(name)} action"

        assert action.type == type,
               "#{inspect(resource)}.#{name} must be a #{type} action, got #{action.type}"
      end

      assert Ash.Resource.Info.primary_action!(resource, :read).name == :read,
             "#{inspect(resource)} must declare :read as its primary read action"
    end

    comment_count = Ash.Resource.Info.aggregate(Forum.Content.Post, :comment_count)
    assert comment_count, "Forum.Content.Post must define a comment_count aggregate"
    assert comment_count.kind == :count, "comment_count must be a count aggregate"

    assert comment_count.relationship_path == [:comments],
           "comment_count must aggregate over :comments"

    reaction_count = Ash.Resource.Info.aggregate(Forum.Content.Comment, :reaction_count)
    assert reaction_count, "Forum.Content.Comment must define a reaction_count aggregate"
    assert reaction_count.kind == :count, "reaction_count must be a count aggregate"

    assert reaction_count.relationship_path == [:reactions],
           "reaction_count must aggregate over :reactions"
  end

  test "s02_shared_modules_are_reused_across_resources" do
    scope = Forum.Archive.Preparations.ArchiveScope
    cascade_archive = Forum.Archive.Changes.CascadeArchive
    cascade_restore = Forum.Archive.Changes.CascadeRestore

    Code.ensure_loaded!(scope)
    Code.ensure_loaded!(cascade_archive)
    Code.ensure_loaded!(cascade_restore)

    assert function_exported?(scope, :prepare, 3),
           "#{inspect(scope)} must implement the Ash.Resource.Preparation behaviour"

    assert function_exported?(cascade_archive, :change, 3),
           "#{inspect(cascade_archive)} must implement the Ash.Resource.Change behaviour"

    assert function_exported?(cascade_restore, :change, 3),
           "#{inspect(cascade_restore)} must implement the Ash.Resource.Change behaviour"

    for resource <- @resources do
      for action <- [:read, :archived, :with_archived] do
        assert scope in H.preparation_modules(resource, action),
               "#{inspect(resource)}.#{action} must be prepared by #{inspect(scope)}"
      end

      assert cascade_archive in H.change_modules(resource, :archive),
             "#{inspect(resource)}.archive must use #{inspect(cascade_archive)}"

      assert cascade_restore in H.change_modules(resource, :restore),
             "#{inspect(resource)}.restore must use #{inspect(cascade_restore)}"
    end
  end

  test "s03_live_reads_return_every_record" do
    H.tree()

    assert H.titles(H.read(Forum.Content.Post)) == ["P"]
    assert H.bodies(H.read(Forum.Content.Comment)) == ["c1", "c2"]
    assert H.emojis(H.read(Forum.Content.Reaction)) == ["r1", "r2"]
  end

  test "s04_archiving_a_post_hides_the_whole_subtree_from_the_primary_read" do
    t = H.tree()
    H.archive!(t.p)

    assert H.read(Forum.Content.Post) == []
    assert H.read(Forum.Content.Comment) == []
    assert H.read(Forum.Content.Reaction) == []

    assert length(H.read(Forum.Content.Post, :with_archived)) == 1
    assert length(H.read(Forum.Content.Comment, :with_archived)) == 2
    assert length(H.read(Forum.Content.Reaction, :with_archived)) == 2
  end

  test "s05_archived_rows_survive_but_get_reports_not_found" do
    t = H.tree()
    H.archive!(t.p)

    assert {:error, error} = Ash.get(Forum.Content.Post, t.p.id, authorize?: false)

    assert Enum.any?(H.flat_errors(error), &match?(%Ash.Error.Query.NotFound{}, &1)),
           "Ash.get/3 on an archived post must produce an Ash.Error.Query.NotFound, got #{inspect(error)}"

    assert H.reload(t.p).id == t.p.id
  end

  test "s06_one_archive_operation_marks_exactly_one_generation" do
    t = H.tree()
    H.archive!(t.p)

    rows = H.reload_all([t.p, t.c1, t.c2, t.r1, t.r2])

    for row <- rows do
      assert row.archived_at, "#{inspect(row.__struct__)} #{row.id} should have been archived"
      assert row.archive_batch_id, "archived rows must carry an archive_batch_id"
    end

    assert rows |> Enum.map(& &1.archived_at) |> Enum.uniq() |> length() == 1,
           "every row archived by one operation must share the same archived_at"

    assert rows |> Enum.map(& &1.archive_batch_id) |> Enum.uniq() |> length() == 1,
           "every row archived by one operation must share the same archive_batch_id"
  end

  test "s07_separate_archive_operations_use_distinct_batches" do
    a = H.tree()
    H.archive!(a.p)
    batch_a = H.reload(a.p).archive_batch_id

    b_post = H.post("Q")
    H.comment(b_post, "q1")
    H.archive!(b_post)
    batch_b = H.reload(b_post).archive_batch_id

    refute batch_a == batch_b, "two archive operations must not share an archive_batch_id"

    c = H.tree()
    H.archive!(c.c1)
    H.archive!(c.c2)

    refute H.reload(c.c1).archive_batch_id == H.reload(c.c2).archive_batch_id,
           "archiving two sibling comments separately must yield distinct batch ids"
  end

  test "s08_archiving_a_comment_cascades_only_to_its_own_reactions" do
    t = H.tree()
    H.archive!(t.c1)

    [c1, r1, p, c2, r2] = H.reload_all([t.c1, t.r1, t.p, t.c2, t.r2])

    assert H.archived?(c1), "the archived comment must be marked archived"
    assert H.archived?(r1), "the archived comment's reaction must be marked archived"
    assert c1.archive_batch_id == r1.archive_batch_id
    assert c1.archived_at == r1.archived_at

    for untouched <- [p, c2, r2] do
      assert H.marks(untouched) == {nil, nil},
             "#{inspect(untouched.__struct__)} #{untouched.id} must stay live"
    end
  end

  test "s09_a_later_archive_leaves_earlier_archived_descendants_alone" do
    t = H.tree()
    H.archive!(t.c1)

    early_c1 = H.marks(H.reload(t.c1))
    early_r1 = H.marks(H.reload(t.r1))

    H.archive!(t.p)

    assert H.marks(H.reload(t.c1)) == early_c1,
           "an already-archived comment must keep its original archived_at and archive_batch_id"

    assert H.marks(H.reload(t.r1)) == early_r1,
           "an already-archived reaction must keep its original archived_at and archive_batch_id"

    [p, c2, r2] = H.reload_all([t.p, t.c2, t.r2])
    assert p.archive_batch_id == c2.archive_batch_id
    assert p.archive_batch_id == r2.archive_batch_id
    refute p.archive_batch_id == elem(early_c1, 1),
           "the second archive operation must allocate a new batch id"
  end

  test "s10_archiving_twice_is_idempotent" do
    t = H.tree()
    H.archive!(t.p)
    before = Enum.map(H.reload_all([t.p, t.c1, t.c2, t.r1, t.r2]), &H.marks/1)

    H.archive!(H.reload(t.p))

    after_second = Enum.map(H.reload_all([t.p, t.c1, t.c2, t.r1, t.r2]), &H.marks/1)

    assert before == after_second,
           "archiving an already-archived record must not change any archive marker"
  end

  test "s11_restore_only_brings_back_its_own_batch" do
    t = H.tree()
    H.archive!(t.c1)
    early_c1 = H.marks(H.reload(t.c1))
    early_r1 = H.marks(H.reload(t.r1))

    H.archive!(t.p)
    restored = H.restore!(H.reload(t.p))

    assert H.marks(restored) == {nil, nil}
    assert H.marks(H.reload(t.c2)) == {nil, nil}
    assert H.marks(H.reload(t.r2)) == {nil, nil}

    assert H.marks(H.reload(t.c1)) == early_c1,
           "restoring the post must not resurrect an independently archived comment"

    assert H.marks(H.reload(t.r1)) == early_r1,
           "restoring the post must not resurrect an independently archived reaction"

    assert H.bodies(H.read(Forum.Content.Comment)) == ["c2"]
    assert H.emojis(H.read(Forum.Content.Reaction)) == ["r2"]
  end

  test "s12_restoring_a_descendant_does_not_touch_ancestors" do
    t = H.tree()
    H.archive!(t.p)
    batch = H.reload(t.p).archive_batch_id

    H.restore!(H.reload(t.c2))

    assert H.marks(H.reload(t.c2)) == {nil, nil}
    assert H.marks(H.reload(t.r2)) == {nil, nil}

    for record <- [t.p, t.c1, t.r1] do
      reloaded = H.reload(record)

      assert H.archived?(reloaded),
             "#{inspect(reloaded.__struct__)} must stay archived when a descendant is restored"

      assert reloaded.archive_batch_id == batch
    end
  end

  test "s13_restore_is_idempotent_and_safe_on_live_records" do
    t = H.tree()
    H.archive!(t.p)

    once = H.restore!(H.reload(t.p))
    assert H.marks(once) == {nil, nil}

    twice = H.restore!(H.reload(t.p))
    assert H.marks(twice) == {nil, nil}

    fresh = H.tree()
    H.restore!(fresh.p)

    for record <- [fresh.p, fresh.c1, fresh.c2, fresh.r1, fresh.r2] do
      assert H.marks(H.reload(record)) == {nil, nil},
             "restoring a live record must not modify anything"
    end
  end

  test "s14_restore_clears_both_archive_markers" do
    t = H.tree()
    H.archive!(t.p)
    H.restore!(H.reload(t.p))

    for record <- [t.p, t.c1, t.c2, t.r1, t.r2] do
      reloaded = H.reload(record)
      assert is_nil(reloaded.archived_at), "archived_at must be cleared on restore"
      assert is_nil(reloaded.archive_batch_id), "archive_batch_id must be cleared on restore"
    end
  end

  test "s15_count_aggregates_exclude_archived_children" do
    t = H.tree()
    H.archive!(t.c1)

    post =
      Forum.Content.Post
      |> Ash.Query.for_read(:with_archived, %{})
      |> Ash.Query.filter(id == ^t.p.id)
      |> Ash.Query.load([:comment_count])
      |> Ash.read_one!(authorize?: false)

    assert post.comment_count == 1,
           "comment_count must ignore archived comments, got #{inspect(post.comment_count)}"

    counts =
      Forum.Content.Comment
      |> Ash.Query.for_read(:with_archived, %{})
      |> Ash.Query.load([:reaction_count])
      |> Ash.read!(authorize?: false)
      |> Map.new(&{&1.body, &1.reaction_count})

    assert counts == %{"c1" => 0, "c2" => 1},
           "reaction_count must ignore archived reactions, got #{inspect(counts)}"

    H.archive!(t.p)

    post_after =
      Forum.Content.Post
      |> Ash.Query.for_read(:with_archived, %{})
      |> Ash.Query.filter(id == ^t.p.id)
      |> Ash.Query.load([:comment_count])
      |> Ash.read_one!(authorize?: false)

    assert post_after.comment_count == 0,
           "once every comment is archived the count aggregate must be 0"
  end

  test "s16_relationship_loads_exclude_archived_children" do
    t = H.tree()
    H.archive!(t.c1)

    post = Ash.load!(t.p, [:comments], authorize?: false)
    assert H.bodies(post.comments) == ["c2"]

    comment = Ash.load!(H.reload(t.c2), [:reactions], authorize?: false)
    assert H.emojis(comment.reactions) == ["r2"]
  end

  test "s17_relationship_filters_exclude_archived_rows" do
    t = H.tree()
    H.archive!(t.c1)

    hidden =
      Forum.Content.Post
      |> Ash.Query.filter(exists(comments, body == "c1"))
      |> Ash.read!(authorize?: false)

    assert hidden == [],
           "a filter traversing :comments must not match an archived comment"

    visible =
      Forum.Content.Post
      |> Ash.Query.filter(exists(comments, body == "c2"))
      |> Ash.read!(authorize?: false)

    assert H.titles(visible) == ["P"]
  end

  test "s18_the_archived_read_requires_an_admin_actor" do
    t = H.tree()
    H.archive!(t.p)

    assert {:ok, [archived_post]} =
             Forum.Content.Post
             |> Ash.Query.for_read(:archived, %{})
             |> Ash.read(actor: %{role: :admin}, authorize?: true)

    assert archived_post.id == t.p.id

    for resource <- @resources, actor <- [%{role: :member}, nil] do
      result =
        resource
        |> Ash.Query.for_read(:archived, %{})
        |> Ash.read(actor: actor, authorize?: true)

      assert match?({:error, %Ash.Error.Forbidden{}}, result),
             "#{inspect(resource)}.archived must be forbidden for actor #{inspect(actor)}, got #{inspect(result)}"
    end

    for resource <- @resources do
      assert {:ok, rows} =
               resource
               |> Ash.Query.for_read(:archived, %{})
               |> Ash.read(actor: %{role: :admin}, authorize?: true)

      assert length(rows) > 0,
             "an admin must see the archived #{inspect(resource)} rows"
    end
  end

  test "s19_every_other_action_stays_open_to_any_actor" do
    for actor <- [%{role: :member}, nil] do
      post =
        Forum.Content.Post
        |> Ash.Changeset.for_create(:create, %{title: "P"}, actor: actor, authorize?: true)
        |> Ash.create!(actor: actor, authorize?: true)

      assert {:ok, _} =
               Forum.Content.Post
               |> Ash.Query.for_read(:read, %{})
               |> Ash.read(actor: actor, authorize?: true)

      assert {:ok, _} =
               Forum.Content.Post
               |> Ash.Query.for_read(:with_archived, %{})
               |> Ash.read(actor: actor, authorize?: true)

      archived =
        post
        |> Ash.Changeset.for_destroy(:archive, %{}, actor: actor, authorize?: true)
        |> Ash.destroy(actor: actor, authorize?: true)

      assert archived == :ok or match?({:ok, _}, archived),
             "archiving must be permitted for actor #{inspect(actor)}, got #{inspect(archived)}"

      restored =
        H.reload(post)
        |> Ash.Changeset.for_update(:restore, %{}, actor: actor, authorize?: true)
        |> Ash.update(actor: actor, authorize?: true)

      assert match?({:ok, _}, restored),
             "restoring must be permitted for actor #{inspect(actor)}, got #{inspect(restored)}"
    end
  end

  test "s20_purge_refuses_a_live_record_and_changes_nothing" do
    t = H.tree()

    assert {:error, %Ash.Error.Invalid{} = error} = H.purge(t.p)

    matching =
      Enum.filter(H.flat_errors(error), fn
        %Ash.Error.Changes.InvalidChanges{fields: fields, message: message} ->
          fields == [:archived_at] and message == "must be archived before it can be purged"

        _ ->
          false
      end)

    assert matching != [],
           "purging a live record must fail with %Ash.Error.Changes.InvalidChanges{fields: [:archived_at], message: \"must be archived before it can be purged\"}, got #{inspect(error)}"

    assert length(H.read(Forum.Content.Post, :with_archived)) == 1
    assert length(H.read(Forum.Content.Comment, :with_archived)) == 2
    assert length(H.read(Forum.Content.Reaction, :with_archived)) == 2
  end

  test "s21_purging_an_archived_post_removes_the_whole_subtree" do
    t = H.tree()
    H.archive!(t.c1)
    H.archive!(t.p)

    H.purge!(H.reload(t.p))

    assert H.read(Forum.Content.Post, :with_archived) == []
    assert H.read(Forum.Content.Comment, :with_archived) == []
    assert H.read(Forum.Content.Reaction, :with_archived) == []
  end

  test "s22_purging_a_comment_removes_only_that_branch" do
    t = H.tree()
    H.archive!(t.c1)

    H.purge!(H.reload(t.c1))

    assert H.bodies(H.read(Forum.Content.Comment, :with_archived)) == ["c2"]
    assert H.emojis(H.read(Forum.Content.Reaction, :with_archived)) == ["r2"]
    assert H.titles(H.read(Forum.Content.Post, :with_archived)) == ["P"]
    assert H.marks(H.reload(t.p)) == {nil, nil}
    assert H.marks(H.reload(t.c2)) == {nil, nil}
  end
end

ExUnit.run()
"""


def _run_contract_suite():
    with open(SCRIPT_PATH, "w", encoding="utf-8") as handle:
        handle.write(ARCHIVE_CONTRACT_EXS)

    env = dict(os.environ)
    env["MIX_ENV"] = "dev"
    env["HEX_OFFLINE"] = "1"

    completed = subprocess.run(
        ["mix", "run", SCRIPT_PATH],
        cwd=PROJECT_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=1800,
    )

    output = (completed.stdout or "") + "\n" + (completed.stderr or "")

    results = {}
    for line in output.splitlines():
        line = line.strip()
        if not line.startswith(RESULT_PREFIX):
            continue
        try:
            payload = json.loads(line[len(RESULT_PREFIX):])
        except json.JSONDecodeError:
            continue
        results[payload["name"]] = payload

    return {
        "returncode": completed.returncode,
        "output": output,
        "results": results,
    }


@pytest.fixture(scope="session")
def contract_run():
    run = _run_contract_suite()
    print("===== [mix run] Begin combined output =====")
    print(run["output"])
    print("===== [mix run] End combined output =====")
    return run


def _scenario(contract_run, name):
    results = contract_run["results"]
    if name not in results:
        pytest.fail(
            f"Scenario {name!r} never reported a result. The Ash project at "
            f"{PROJECT_DIR} most likely failed to compile or to boot "
            f"(mix run exit code {contract_run['returncode']}).\n"
            f"Combined output:\n{contract_run['output'][-8000:]}"
        )

    payload = results[name]
    assert payload["status"] == "pass", (
        f"Scenario {name!r} did not pass ({payload['status']}).\n"
        f"{payload.get('message', '')}"
    )


def test_contract_suite_executed(contract_run):
    assert contract_run["results"], (
        "The ExUnit contract suite produced no results at all; the project at "
        f"{PROJECT_DIR} could not be compiled or run (exit code "
        f"{contract_run['returncode']}).\n"
        f"Combined output:\n{contract_run['output'][-8000:]}"
    )
    assert contract_run["returncode"] == 0, (
        "`mix run` exited with a non-zero status while executing the contract "
        f"suite (exit code {contract_run['returncode']}).\n"
        f"Combined output:\n{contract_run['output'][-8000:]}"
    )


def test_s01_structure_resources_actions_and_attributes(contract_run):
    _scenario(contract_run, "s01_structure_resources_actions_and_attributes")

def test_s02_shared_modules_are_reused_across_resources(contract_run):
    _scenario(contract_run, "s02_shared_modules_are_reused_across_resources")

def test_s03_live_reads_return_every_record(contract_run):
    _scenario(contract_run, "s03_live_reads_return_every_record")

def test_s04_archiving_a_post_hides_the_whole_subtree_from_the_primary_read(contract_run):
    _scenario(contract_run, "s04_archiving_a_post_hides_the_whole_subtree_from_the_primary_read")

def test_s05_archived_rows_survive_but_get_reports_not_found(contract_run):
    _scenario(contract_run, "s05_archived_rows_survive_but_get_reports_not_found")

def test_s06_one_archive_operation_marks_exactly_one_generation(contract_run):
    _scenario(contract_run, "s06_one_archive_operation_marks_exactly_one_generation")

def test_s07_separate_archive_operations_use_distinct_batches(contract_run):
    _scenario(contract_run, "s07_separate_archive_operations_use_distinct_batches")

def test_s08_archiving_a_comment_cascades_only_to_its_own_reactions(contract_run):
    _scenario(contract_run, "s08_archiving_a_comment_cascades_only_to_its_own_reactions")

def test_s09_a_later_archive_leaves_earlier_archived_descendants_alone(contract_run):
    _scenario(contract_run, "s09_a_later_archive_leaves_earlier_archived_descendants_alone")

def test_s10_archiving_twice_is_idempotent(contract_run):
    _scenario(contract_run, "s10_archiving_twice_is_idempotent")

def test_s11_restore_only_brings_back_its_own_batch(contract_run):
    _scenario(contract_run, "s11_restore_only_brings_back_its_own_batch")

def test_s12_restoring_a_descendant_does_not_touch_ancestors(contract_run):
    _scenario(contract_run, "s12_restoring_a_descendant_does_not_touch_ancestors")

def test_s13_restore_is_idempotent_and_safe_on_live_records(contract_run):
    _scenario(contract_run, "s13_restore_is_idempotent_and_safe_on_live_records")

def test_s14_restore_clears_both_archive_markers(contract_run):
    _scenario(contract_run, "s14_restore_clears_both_archive_markers")

def test_s15_count_aggregates_exclude_archived_children(contract_run):
    _scenario(contract_run, "s15_count_aggregates_exclude_archived_children")

def test_s16_relationship_loads_exclude_archived_children(contract_run):
    _scenario(contract_run, "s16_relationship_loads_exclude_archived_children")

def test_s17_relationship_filters_exclude_archived_rows(contract_run):
    _scenario(contract_run, "s17_relationship_filters_exclude_archived_rows")

def test_s18_the_archived_read_requires_an_admin_actor(contract_run):
    _scenario(contract_run, "s18_the_archived_read_requires_an_admin_actor")

def test_s19_every_other_action_stays_open_to_any_actor(contract_run):
    _scenario(contract_run, "s19_every_other_action_stays_open_to_any_actor")

def test_s20_purge_refuses_a_live_record_and_changes_nothing(contract_run):
    _scenario(contract_run, "s20_purge_refuses_a_live_record_and_changes_nothing")

def test_s21_purging_an_archived_post_removes_the_whole_subtree(contract_run):
    _scenario(contract_run, "s21_purging_an_archived_post_removes_the_whole_subtree")

def test_s22_purging_a_comment_removes_only_that_branch(contract_run):
    _scenario(contract_run, "s22_purging_a_comment_removes_only_that_branch")
