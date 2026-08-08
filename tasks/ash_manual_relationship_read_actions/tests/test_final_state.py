"""Final-state verification for `ash_manual_relationship_read_actions`.

The whole contract is checked by a single self-contained ExUnit suite that is
written to /tmp at verification time and executed with `mix run` inside
/home/user/thread_graph. The suite prints one line per scenario, which is turned
into one pytest function per scenario below so failures are reported granularly.
"""

import base64
import os
import subprocess

import pytest

PROJECT_DIR = "/home/user/thread_graph"
SCRIPT_PATH = "/tmp/harbor_manual_graph.exs"
MARKER = "@@HARBOR@@"
TIMEOUT_SECONDS = 1800

SUITE_EXS = r"""
Logger.configure(level: :warning)

require Ash.Query

defmodule Harbor.Fixtures do
  @moduledoc false
  require Ash.Query

  alias ThreadGraph.Forum.{Author, Message, MessageLink, Thread}

  @threads [
    {"t1", "general", false},
    {"t2", "general", false},
    {"t3", "random", false},
    {"t4", "random", false},
    {"t5", "support", false},
    {"t6", "general", false},
    {"t7", "forkzone", true},
    {"t8", "support", false},
    {"t9", "support", false},
    {"t10", "forkzone", false},
    {"t11", "filler", false},
    {"t12", "filler", false},
    {"t13", "filler", false},
    {"t14", "filler", false}
  ]

  @messages [
    {"alpha-1", 1, 0, "t1", nil, "ana"},
    {"alpha-2", 2, 0, "t1", nil, "bo"},
    {"alpha-3", 3, 0, "t1", nil, "cy"},
    {"alpha-4", 4, 0, "t1", nil, "ana"},
    {"alpha-5", 5, 0, "t1", nil, "bo"},
    {"beta-1", 10, 0, "t2", nil, "ana"},
    {"beta-2", 20, 0, "t2", nil, "bo"},
    {"beta-3", 21, 0, "t2", nil, "cy"},
    {"gamma-1", 7, 0, "t3", nil, "ana"},
    {"gamma-2", 8, 50, "t3", nil, "bo"},
    {"gamma-3", 9, 0, "t3", nil, "cy"},
    {"gamma-4", 6, 60, "t3", nil, "ana"},
    {"graph-1", 1, 0, "t5", nil, "ana"},
    {"graph-2", 2, 0, "t5", nil, "ana"},
    {"graph-3", 3, 0, "t5", nil, "ana"},
    {"graph-4", 4, 0, "t5", nil, "ana"},
    {"graph-5", 5, 0, "t5", nil, "ana"},
    {"graph-6", 6, 0, "t5", nil, "ana"},
    {"zeta-1", 1, 0, "t6", nil, "ana"},
    {"zeta-2", 1, 0, "t6", nil, "bo"},
    {"lock-1", 1, 0, "t7", nil, "ana"},
    {"chain-0", 1, 0, "t8", nil, "ana"},
    {"chain-1", 2, 0, "t8", "chain-0", "bo"},
    {"chain-2", 3, 0, "t8", "chain-1", "ana"},
    {"chain-3a", 4, 0, "t8", "chain-2", "bo"},
    {"chain-3b", 5, 0, "t8", "chain-2", "cy"},
    {"cycle-1", 1, 0, "t9", nil, "ana"},
    {"cycle-2", 2, 0, "t9", "cycle-1", "bo"},
    {"fork-1", 5, 1, "t10", nil, "ana"},
    {"fork-2", 3, 2, "t10", "fork-1", "bo"},
    {"fork-3", 9, 3, "t10", "fork-2", "cy"},
    {"fork-4", 1, 4, "t10", "fork-1", nil},
    {"fork-5", 7, 5, "t10", nil, "ana"},
    {"fork-6", 2, 6, "t10", "fork-5", "bo"},
    {"filler-1a", 1, 0, "t11", nil, "ana"},
    {"filler-1b", 2, 0, "t11", nil, "ana"},
    {"filler-2a", 1, 0, "t12", nil, "ana"},
    {"filler-2b", 2, 0, "t12", nil, "ana"},
    {"filler-3a", 1, 0, "t13", nil, "ana"},
    {"filler-3b", 2, 0, "t13", nil, "ana"},
    {"filler-4a", 1, 0, "t14", nil, "ana"},
    {"filler-4b", 2, 0, "t14", nil, "ana"}
  ]

  @links [
    {"graph-1", "graph-2", :follow_up},
    {"graph-1", "graph-3", :follow_up},
    {"graph-2", "graph-4", :follow_up},
    {"graph-3", "graph-4", :follow_up},
    {"graph-4", "graph-5", :follow_up},
    {"graph-5", "graph-1", :follow_up},
    {"alpha-2", "alpha-1", :follow_up},
    {"alpha-3", "alpha-1", :follow_up},
    {"alpha-4", "alpha-1", :follow_up},
    {"alpha-5", "alpha-2", :follow_up},
    {"beta-1", "alpha-2", :duplicate_of},
    {"beta-2", "beta-1", :follow_up},
    {"beta-3", "beta-1", :follow_up},
    {"beta-1", "zeta-1", :follow_up}
  ]

  @key {__MODULE__, :data}

  def seed! do
    authors =
      Map.new(["ana", "bo", "cy"], fn handle ->
        {handle,
         Author
         |> Ash.Changeset.for_create(:create, %{
           handle: handle,
           display_name: String.upcase(handle)
         })
         |> Ash.create!()}
      end)

    threads =
      Map.new(@threads, fn {slug, board, locked} ->
        {slug,
         Thread
         |> Ash.Changeset.for_create(:create, %{
           slug: slug,
           title: String.upcase(slug),
           board: board,
           locked: locked
         })
         |> Ash.create!()}
      end)

    messages =
      Enum.reduce(@messages, %{}, fn {body, position, score, slug, parent, author}, acc ->
        message =
          Message
          |> Ash.Changeset.for_create(:create, %{
            body: body,
            position: position,
            score: score,
            thread_id: Map.fetch!(threads, slug).id,
            parent_id: parent && Map.fetch!(acc, parent).id,
            author_id: author && Map.fetch!(authors, author).id
          })
          |> Ash.create!()

        Map.put(acc, body, message)
      end)

    cycle_1 =
      messages["cycle-1"]
      |> Ash.Changeset.for_update(:update, %{parent_id: messages["cycle-2"].id})
      |> Ash.update!()

    messages = Map.put(messages, "cycle-1", cycle_1)

    for {from, to, kind} <- @links do
      MessageLink
      |> Ash.Changeset.for_create(:create, %{
        kind: kind,
        from_message_id: Map.fetch!(messages, from).id,
        to_message_id: Map.fetch!(messages, to).id
      })
      |> Ash.create!()
    end

    :persistent_term.put(@key, %{authors: authors, threads: threads, messages: messages})
    :ok
  end

  def data, do: :persistent_term.get(@key)
  def message(body), do: Map.fetch!(data().messages, body)
  def thread(slug), do: Map.fetch!(data().threads, slug)
  def message_id(body), do: message(body).id
  def thread_id(slug), do: thread(slug).id
end

defmodule Harbor.Helpers do
  @moduledoc false

  def bodies(records) when is_list(records), do: Enum.map(records, & &1.body)
  def bodies(other), do: other

  def manual_module({mod, _opts}), do: mod
  def manual_module(mod), do: mod

  @doc "Runs `fun` while counting Ash read actions emitted through :telemetry."
  def with_read_count(fun) do
    parent = self()
    ref = make_ref()
    handler_id = "harbor-reads-#{System.unique_integer([:positive])}"

    :telemetry.attach(
      handler_id,
      [:ash, :forum, :read, :stop],
      fn _event, _measurements, _metadata, _config -> send(parent, {ref, :read}) end,
      nil
    )

    result =
      try do
        fun.()
      after
        Process.sleep(25)
        :telemetry.detach(handler_id)
      end

    {result, drain(ref, 0)}
  end

  defp drain(ref, acc) do
    receive do
      {^ref, :read} -> drain(ref, acc + 1)
    after
      0 -> acc
    end
  end
end

defmodule Harbor.Formatter do
  @moduledoc false
  use GenServer

  @impl true
  def init(opts), do: {:ok, opts}

  @impl true
  def handle_cast({:test_finished, %ExUnit.Test{} = test}, state) do
    {status, detail} =
      case test.state do
        nil ->
          {"PASS", ""}

        {:excluded, reason} ->
          {"FAIL", "excluded: #{inspect(reason)}"}

        {:skipped, reason} ->
          {"FAIL", "skipped: #{inspect(reason)}"}

        {:invalid, module} ->
          {"FAIL", "invalid test module: #{inspect(module)}"}

        {:failed, failed} ->
          {"FAIL",
           ExUnit.Formatter.format_test_failure(test, failed, 1, 160, fn _kind, message ->
             message
           end)}
      end

    IO.puts("@@HARBOR@@#{test.name}@@#{status}@@#{Base.encode64(detail)}")
    {:noreply, state}
  end

  def handle_cast(_message, state), do: {:noreply, state}
end

Harbor.Fixtures.seed!()

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

  import Harbor.Helpers

  alias Harbor.Fixtures, as: F
  alias ThreadGraph.Forum.{Message, MessageLink, Thread}

  @counter ThreadGraph.Forum.LoadCounter
  @seeded_slugs ~w(t1 t2 t3 t4 t5 t6 t7 t8 t9 t10 t11 t12 t13 t14)

  test "T01 manual relationships are declared and delegate to the required modules" do
    expected = [
      {Thread, :recent_messages, ThreadGraph.Forum.Threads.RecentMessages},
      {Message, :ancestor_messages, ThreadGraph.Forum.Messages.AncestorMessages},
      {Message, :linked_messages, ThreadGraph.Forum.Messages.LinkedMessages}
    ]

    for {resource, name, module} <- expected do
      relationship = Ash.Resource.Info.relationship(resource, name)

      assert relationship, "#{inspect(resource)} has no relationship named #{inspect(name)}"
      assert relationship.type == :has_many, "#{name} must be a has_many relationship"

      assert relationship.destination == Message,
             "#{name} must point at ThreadGraph.Forum.Message"

      assert relationship.public? == true, "#{name} must be public"

      assert manual_module(relationship.manual) == module,
             "#{name} must be implemented by #{inspect(module)}, got #{inspect(relationship.manual)}"
    end
  end

  test "T02 manual actions are declared and delegate to the required modules" do
    read = Ash.Resource.Info.action(Message, :cross_board_highlights)
    assert read, "Message has no :cross_board_highlights action"
    assert read.type == :read, ":cross_board_highlights must be a read action"

    assert manual_module(read.manual) == ThreadGraph.Forum.Messages.CrossBoardHighlights,
           "unexpected manual module: #{inspect(read.manual)}"

    create = Ash.Resource.Info.action(Thread, :fork)
    assert create, "Thread has no :fork action"
    assert create.type == :create, ":fork must be a create action"

    assert manual_module(create.manual) == ThreadGraph.Forum.Threads.ForkThread,
           "unexpected manual module: #{inspect(create.manual)}"
  end

  test "T03 manual actions expose exactly the required arguments" do
    read = Ash.Resource.Info.action(Message, :cross_board_highlights)
    read_args = Map.new(read.arguments, &{&1.name, &1})

    assert Enum.sort(Map.keys(read_args)) == [:boards, :min_endorsements],
           "unexpected arguments: #{inspect(Map.keys(read_args))}"

    assert Ash.Type.get_type(read_args[:boards].type) == Ash.Type.get_type({:array, :string})
    assert read_args[:boards].allow_nil? == false, ":boards must be required"
    assert Ash.Type.get_type(read_args[:min_endorsements].type) == Ash.Type.get_type(:integer)
    assert read_args[:min_endorsements].default == 0, ":min_endorsements must default to 0"

    create = Ash.Resource.Info.action(Thread, :fork)
    create_args = Map.new(create.arguments, &{&1.name, &1})

    assert Enum.sort(Map.keys(create_args)) == [:slug, :source_message_id, :title],
           "unexpected arguments: #{inspect(Map.keys(create_args))}"

    assert Ash.Type.get_type(create_args[:source_message_id].type) == Ash.Type.get_type(:uuid)
    assert Ash.Type.get_type(create_args[:slug].type) == Ash.Type.get_type(:string)
    assert Ash.Type.get_type(create_args[:title].type) == Ash.Type.get_type(:string)

    for name <- [:source_message_id, :slug, :title] do
      assert create_args[name].allow_nil? == false, "#{name} must be required"
    end

    assert create.accept == [], ":fork must not accept any attribute"
  end

  test "T04 reply_count aggregate counts direct replies" do
    messages =
      Message
      |> Ash.Query.filter(thread_id == ^F.thread_id("t8"))
      |> Ash.Query.load(:reply_count)
      |> Ash.read!()
      |> Map.new(&{&1.body, &1.reply_count})

    assert messages == %{
             "chain-0" => 1,
             "chain-1" => 1,
             "chain-2" => 2,
             "chain-3a" => 0,
             "chain-3b" => 0
           }
  end

  test "T05 recent_messages returns the top 3 per thread, not a global top 3" do
    threads = load_all_threads()

    assert bodies(threads["t1"].recent_messages) == ["alpha-5", "alpha-4", "alpha-3"]
    assert bodies(threads["t2"].recent_messages) == ["beta-3", "beta-2", "beta-1"]
    assert bodies(threads["t3"].recent_messages) == ["gamma-3", "gamma-2", "gamma-1"]
    assert bodies(threads["t8"].recent_messages) == ["chain-3b", "chain-3a", "chain-2"]
  end

  test "T06 recent_messages yields [] for a thread without messages" do
    threads = load_all_threads()
    assert threads["t4"].recent_messages == []
  end

  test "T07 recent_messages returns fewer than 3 entries when there are fewer messages" do
    threads = load_all_threads()

    assert length(threads["t9"].recent_messages) == 2
    assert length(threads["t7"].recent_messages) == 1
    assert bodies(threads["t7"].recent_messages) == ["lock-1"]
  end

  test "T08 recent_messages breaks a position tie with an ascending id" do
    threads = load_all_threads()

    expected = Enum.sort([F.message_id("zeta-1"), F.message_id("zeta-2")])
    assert Enum.map(threads["t6"].recent_messages, & &1.id) == expected
  end

  test "T09 recent_messages applies the load query filter before truncating" do
    threads =
      Thread
      |> Ash.Query.load(recent_messages: Ash.Query.filter(Message, score >= 50))
      |> Ash.read!()
      |> Map.new(&{&1.slug, &1})

    assert bodies(threads["t3"].recent_messages) == ["gamma-2", "gamma-4"]
    assert threads["t1"].recent_messages == []
  end

  test "T10 recent_messages is loaded in a single batch for every parent" do
    @counter.reset()

    threads =
      Thread
      |> Ash.Query.filter(slug in ^@seeded_slugs)
      |> Ash.Query.load(:recent_messages)
      |> Ash.read!()

    assert length(threads) == 14
    assert @counter.count(:recent_messages) == 1
  end

  test "T11 recent_messages does not issue a read per parent record" do
    threads =
      Thread
      |> Ash.Query.filter(slug in ^@seeded_slugs)
      |> Ash.read!()

    assert length(threads) == 14

    {loaded, reads} = with_read_count(fn -> Ash.load!(threads, :recent_messages) end)

    assert length(loaded) == 14
    assert reads <= 8, "loading recent_messages for 14 threads issued #{reads} read actions"
  end

  test "T12 a normal relationship loads underneath a manual relationship" do
    thread =
      Thread
      |> Ash.Query.filter(slug == "t8")
      |> Ash.Query.load(recent_messages: [:author])
      |> Ash.read_one!()

    assert bodies(thread.recent_messages) == ["chain-3b", "chain-3a", "chain-2"]
    assert Enum.map(thread.recent_messages, & &1.author.handle) == ["cy", "bo", "ana"]
  end

  test "T13 an aggregate loads underneath a manual relationship" do
    thread =
      Thread
      |> Ash.Query.filter(slug == "t8")
      |> Ash.Query.load(recent_messages: [:reply_count])
      |> Ash.read_one!()

    assert Enum.map(thread.recent_messages, & &1.reply_count) == [0, 0, 2]
  end

  test "T14 a manual relationship loads underneath another manual relationship" do
    thread =
      Thread
      |> Ash.Query.filter(slug == "t8")
      |> Ash.Query.load(recent_messages: [:ancestor_messages])
      |> Ash.read_one!()

    assert Enum.map(thread.recent_messages, &bodies(&1.ancestor_messages)) == [
             ["chain-0", "chain-1", "chain-2"],
             ["chain-0", "chain-1", "chain-2"],
             ["chain-0", "chain-1"]
           ]
  end

  test "T15 ancestor_messages walks the whole parent chain, outermost first" do
    ancestors = load_ancestors()

    assert ancestors["chain-0"] == []
    assert ancestors["chain-1"] == ["chain-0"]
    assert ancestors["chain-2"] == ["chain-0", "chain-1"]
    assert ancestors["chain-3a"] == ["chain-0", "chain-1", "chain-2"]
    assert ancestors["chain-3b"] == ["chain-0", "chain-1", "chain-2"]
  end

  test "T16 ancestor_messages terminates on a cyclic parent chain" do
    ancestors = load_ancestors()

    assert ancestors["cycle-1"] == ["cycle-2"]
    assert ancestors["cycle-2"] == ["cycle-1"]
  end

  test "T17 ancestor_messages is batched and does not issue a read per parent record" do
    @counter.reset()

    messages = ancestor_targets()
    assert length(messages) == 13

    {loaded, reads} = with_read_count(fn -> Ash.load!(messages, :ancestor_messages) end)

    assert length(loaded) == 13
    assert @counter.count(:ancestor_messages) == 1
    assert reads <= 8, "loading ancestor_messages for 13 messages issued #{reads} read actions"
  end

  test "T18 linked_messages returns the transitive closure ordered by hop distance" do
    linked = load_linked()

    assert linked["graph-1"] == ["graph-2", "graph-3", "graph-4", "graph-5"]
    assert linked["graph-5"] == ["graph-1", "graph-2", "graph-3", "graph-4"]
    assert linked["graph-4"] == ["graph-5", "graph-1", "graph-2", "graph-3"]
  end

  test "T19 linked_messages excludes the source in a cycle and yields [] without edges" do
    linked = load_linked()

    refute "graph-1" in linked["graph-1"]
    assert linked["graph-6"] == []
    assert linked["alpha-1"] == []
  end

  test "T20 linked_messages ignores the edge kind and shares targets between sources" do
    linked = load_linked()

    assert linked["beta-1"] == ["zeta-1", "alpha-2", "alpha-1"]
    assert linked["alpha-3"] == ["alpha-1"]
    assert linked["alpha-5"] == ["alpha-2", "alpha-1"]
  end

  test "T21 linked_messages is batched and does not issue a read per parent record" do
    @counter.reset()

    messages = linked_targets()
    assert length(messages) == 14

    {loaded, reads} = with_read_count(fn -> Ash.load!(messages, :linked_messages) end)

    assert length(loaded) == 14
    assert @counter.count(:linked_messages) == 1
    assert reads <= 8, "loading linked_messages for 14 messages issued #{reads} read actions"
  end

  test "T22 cross_board_highlights scopes by board and applies the default ordering" do
    assert bodies(highlights(["general"], 0)) == [
             "alpha-1",
             "beta-1",
             "zeta-1",
             "alpha-2",
             "zeta-2",
             "alpha-3",
             "alpha-4",
             "alpha-5",
             "beta-2",
             "beta-3"
           ]
  end

  test "T23 cross_board_highlights honours the min_endorsements threshold" do
    assert bodies(highlights(["general"], 2)) == ["alpha-1", "beta-1"]
    assert bodies(highlights(["general"], 1)) == ["alpha-1", "beta-1", "zeta-1", "alpha-2"]
  end

  test "T24 cross_board_highlights merges several boards" do
    assert bodies(highlights(["general", "random"], 0)) == [
             "alpha-1",
             "beta-1",
             "zeta-1",
             "alpha-2",
             "zeta-2",
             "alpha-3",
             "alpha-4",
             "alpha-5",
             "gamma-4",
             "gamma-1",
             "gamma-2",
             "gamma-3",
             "beta-2",
             "beta-3"
           ]
  end

  test "T25 cross_board_highlights attaches the endorsement count as metadata" do
    counts =
      ["general"]
      |> highlights(1)
      |> Enum.map(&Ash.Resource.get_metadata(&1, :endorsement_count))

    assert counts == [3, 2, 1, 1]
  end

  test "T26 cross_board_highlights honours a filter carried by the query" do
    results =
      Message
      |> Ash.Query.for_read(:cross_board_highlights, %{
        boards: ["general", "random"],
        min_endorsements: 0
      })
      |> Ash.Query.filter(score >= 50)
      |> Ash.read!()

    assert bodies(results) == ["gamma-4", "gamma-2"]
  end

  test "T27 a sort carried by the query replaces the default ordering" do
    results =
      Message
      |> Ash.Query.for_read(:cross_board_highlights, %{boards: ["general"], min_endorsements: 1})
      |> Ash.Query.sort(body: :asc)
      |> Ash.read!()

    assert bodies(results) == ["alpha-1", "alpha-2", "beta-1", "zeta-1"]
  end

  test "T28 cross_board_highlights honours limit and offset" do
    limited =
      Message
      |> Ash.Query.for_read(:cross_board_highlights, %{boards: ["general"], min_endorsements: 0})
      |> Ash.Query.sort(body: :asc)
      |> Ash.Query.limit(3)
      |> Ash.read!()

    assert bodies(limited) == ["alpha-1", "alpha-2", "alpha-3"]

    paged =
      Message
      |> Ash.Query.for_read(:cross_board_highlights, %{boards: ["general"], min_endorsements: 0})
      |> Ash.Query.sort(body: :asc)
      |> Ash.Query.offset(2)
      |> Ash.Query.limit(2)
      |> Ash.read!()

    assert bodies(paged) == ["alpha-3", "alpha-4"]
  end

  test "T29 the code interface exposes cross_board_highlights and runs it once" do
    expected = bodies(highlights(["general"], 1))

    @counter.reset()
    from_interface = apply(ThreadGraph.Forum, :highlights!, [["general"], 1])
    assert @counter.count(:cross_board_highlights) == 1

    assert bodies(from_interface) == expected
    assert {:ok, list} = apply(ThreadGraph.Forum, :highlights, [["general"], 1])
    assert bodies(list) == ["alpha-1", "beta-1", "zeta-1", "alpha-2"]
  end

  test "T30 fork copies the source message and its descendants into a new thread" do
    thread = apply(ThreadGraph.Forum, :fork_thread!, [F.message_id("fork-2"), "fk-a", "Fork A"])

    assert thread.slug == "fk-a"
    assert thread.title == "Fork A"
    assert thread.board == "forkzone"
    assert thread.locked == false

    copies = thread_messages(thread.id)
    assert Enum.map(copies, & &1.body) == ["fork-2", "fork-3"]
    assert Enum.map(copies, & &1.position) == [1, 2]
    assert Enum.map(copies, & &1.score) == [2, 3]

    [root, child] = copies
    assert root.parent_id == nil
    assert child.parent_id == root.id
    assert root.id != F.message_id("fork-2")
    assert child.id != F.message_id("fork-3")
    assert root.author_id == F.message("fork-2").author_id
    assert child.author_id == F.message("fork-3").author_id
  end

  test "T31 fork renumbers positions by position order and ignores unrelated messages" do
    thread = apply(ThreadGraph.Forum, :fork_thread!, [F.message_id("fork-1"), "fk-b", "Fork B"])

    copies = thread_messages(thread.id)
    assert Enum.map(copies, & &1.body) == ["fork-4", "fork-2", "fork-1", "fork-3"]
    assert Enum.map(copies, & &1.position) == [1, 2, 3, 4]

    by_body = Map.new(copies, &{&1.body, &1})
    assert by_body["fork-1"].parent_id == nil
    assert by_body["fork-2"].parent_id == by_body["fork-1"].id
    assert by_body["fork-4"].parent_id == by_body["fork-1"].id
    assert by_body["fork-3"].parent_id == by_body["fork-2"].id

    refute Map.has_key?(by_body, "fork-5")
    refute Map.has_key?(by_body, "fork-6")
  end

  test "T32 fork records exactly one :fork_of link from the new root to the source" do
    thread = apply(ThreadGraph.Forum, :fork_thread!, [F.message_id("fork-5"), "fk-c", "Fork C"])

    copies = thread_messages(thread.id)
    assert Enum.map(copies, & &1.body) == ["fork-6", "fork-5"]

    links =
      MessageLink
      |> Ash.Query.filter(kind == :fork_of and to_message_id == ^F.message_id("fork-5"))
      |> Ash.read!()

    assert length(links) == 1
    [link] = links

    root = Enum.find(copies, &(&1.parent_id == nil))
    assert root.body == "fork-5"
    assert link.from_message_id == root.id
  end

  test "T33 fork rejects an unknown source message without writing anything" do
    before = totals()

    result =
      Thread
      |> Ash.Changeset.for_create(:fork, %{
        source_message_id: Ash.UUID.generate(),
        slug: "fk-missing",
        title: "Missing"
      })
      |> Ash.create()

    assert {:error, %Ash.Error.Invalid{} = error} = result

    assert Enum.any?(error.errors, fn
             %Ash.Error.Changes.InvalidArgument{field: :source_message_id, message: message} ->
               message == "source message not found"

             _ ->
               false
           end),
           "unexpected errors: #{inspect(error.errors)}"

    assert totals() == before, "the failed fork left records behind"
  end

  test "T34 fork rejects a locked source thread without writing anything" do
    before = totals()

    result =
      Thread
      |> Ash.Changeset.for_create(:fork, %{
        source_message_id: F.message_id("lock-1"),
        slug: "fk-locked",
        title: "Locked"
      })
      |> Ash.create()

    assert {:error, %Ash.Error.Invalid{} = error} = result

    assert Enum.any?(error.errors, fn
             %Ash.Error.Changes.InvalidArgument{field: :source_message_id, message: message} ->
               message == "source thread is locked"

             _ ->
               false
           end),
           "unexpected errors: #{inspect(error.errors)}"

    assert totals() == before, "the failed fork left records behind"
  end

  test "T35 the fork code interface runs the manual action exactly once" do
    @counter.reset()

    assert {:ok, thread} =
             apply(ThreadGraph.Forum, :fork_thread, [F.message_id("fork-4"), "fk-d", "Fork D"])

    assert thread.slug == "fk-d"
    assert @counter.count(:fork) == 1

    copies = thread_messages(thread.id)
    assert Enum.map(copies, & &1.body) == ["fork-4"]
    assert Enum.map(copies, & &1.position) == [1]
  end

  defp load_all_threads do
    Thread
    |> Ash.Query.load(:recent_messages)
    |> Ash.read!()
    |> Map.new(&{&1.slug, &1})
  end

  defp ancestor_targets do
    Message
    |> Ash.Query.filter(
      thread_id in ^[F.thread_id("t8"), F.thread_id("t9"), F.thread_id("t10")]
    )
    |> Ash.read!()
  end

  defp linked_targets do
    Message
    |> Ash.Query.filter(thread_id in ^[F.thread_id("t1"), F.thread_id("t2"), F.thread_id("t5")])
    |> Ash.read!()
  end

  defp load_ancestors do
    ancestor_targets()
    |> Ash.load!(:ancestor_messages)
    |> Map.new(&{&1.body, bodies(&1.ancestor_messages)})
  end

  defp load_linked do
    linked_targets()
    |> Ash.load!(:linked_messages)
    |> Map.new(&{&1.body, bodies(&1.linked_messages)})
  end

  defp highlights(boards, min_endorsements) do
    Message
    |> Ash.Query.for_read(:cross_board_highlights, %{
      boards: boards,
      min_endorsements: min_endorsements
    })
    |> Ash.read!()
  end

  defp thread_messages(tid) do
    Message
    |> Ash.Query.filter(thread_id == ^tid)
    |> Ash.read!()
    |> Enum.sort_by(& &1.position)
  end

  defp totals do
    {length(Ash.read!(Thread)), length(Ash.read!(Message)), length(Ash.read!(MessageLink))}
  end
end

ExUnit.run()
"""


def _tail(text: str, limit: int = 6000) -> str:
    if len(text) <= limit:
        return text
    return "... (truncated) ...\n" + text[-limit:]


@pytest.fixture(scope="session")
def suite():
    """Runs the ExUnit contract suite once and returns its per-scenario results."""
    if os.path.exists(SCRIPT_PATH):
        os.remove(SCRIPT_PATH)

    with open(SCRIPT_PATH, "w", encoding="utf-8") as handle:
        handle.write(SUITE_EXS.lstrip("\n"))

    env = dict(os.environ)
    env["MIX_ENV"] = "dev"

    try:
        process = subprocess.run(
            ["mix", "run", SCRIPT_PATH],
            cwd=PROJECT_DIR,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
            env=env,
        )
        stdout, stderr, returncode = process.stdout, process.stderr, process.returncode
    except subprocess.TimeoutExpired as expired:
        stdout = expired.stdout.decode("utf-8", "replace") if expired.stdout else ""
        stderr = expired.stderr.decode("utf-8", "replace") if expired.stderr else ""
        stderr += "\n`mix run` timed out."
        returncode = -1
    finally:
        if os.path.exists(SCRIPT_PATH):
            os.remove(SCRIPT_PATH)

    results = {}
    for line in stdout.splitlines():
        if not line.startswith(MARKER):
            continue
        parts = line.split("@@")
        if len(parts) < 5:
            continue
        name, status, encoded = parts[2], parts[3], parts[4]
        words = name.split()
        if len(words) < 2:
            continue
        try:
            detail = base64.b64decode(encoded).decode("utf-8", "replace")
        except Exception:  # pragma: no cover - defensive
            detail = encoded
        results[words[1]] = (status, detail)

    diagnostics = (
        f"`mix run {SCRIPT_PATH}` exited with {returncode}.\n"
        f"--- stdout ---\n{_tail(stdout)}\n--- stderr ---\n{_tail(stderr)}"
    )
    return results, diagnostics


def _assert_scenario(suite, scenario_id):
    results, diagnostics = suite
    assert scenario_id in results, (
        f"Scenario {scenario_id} did not run. The project most likely failed to "
        f"compile or the suite crashed.\n{diagnostics}"
    )
    status, detail = results[scenario_id]
    assert status == "PASS", f"Scenario {scenario_id} failed:\n{detail}"


def test_t01_manual_relationships_declare_their_modules(suite):
    _assert_scenario(suite, "T01")


def test_t02_manual_actions_declare_their_modules(suite):
    _assert_scenario(suite, "T02")


def test_t03_manual_actions_expose_the_required_arguments(suite):
    _assert_scenario(suite, "T03")


def test_t04_reply_count_aggregate_counts_direct_replies(suite):
    _assert_scenario(suite, "T04")


def test_t05_recent_messages_is_a_per_thread_top_three(suite):
    _assert_scenario(suite, "T05")


def test_t06_recent_messages_is_empty_for_a_thread_without_messages(suite):
    _assert_scenario(suite, "T06")


def test_t07_recent_messages_returns_fewer_than_three_when_available(suite):
    _assert_scenario(suite, "T07")


def test_t08_recent_messages_breaks_position_ties_by_ascending_id(suite):
    _assert_scenario(suite, "T08")


def test_t09_recent_messages_filters_before_truncating(suite):
    _assert_scenario(suite, "T09")


def test_t10_recent_messages_is_loaded_in_one_batch(suite):
    _assert_scenario(suite, "T10")


def test_t11_recent_messages_does_not_query_per_parent(suite):
    _assert_scenario(suite, "T11")


def test_t12_relationship_loads_under_a_manual_relationship(suite):
    _assert_scenario(suite, "T12")


def test_t13_aggregate_loads_under_a_manual_relationship(suite):
    _assert_scenario(suite, "T13")


def test_t14_manual_relationship_loads_under_a_manual_relationship(suite):
    _assert_scenario(suite, "T14")


def test_t15_ancestor_messages_is_ordered_outermost_first(suite):
    _assert_scenario(suite, "T15")


def test_t16_ancestor_messages_terminates_on_a_cycle(suite):
    _assert_scenario(suite, "T16")


def test_t17_ancestor_messages_is_batched(suite):
    _assert_scenario(suite, "T17")


def test_t18_linked_messages_is_a_transitive_closure(suite):
    _assert_scenario(suite, "T18")


def test_t19_linked_messages_excludes_self_and_handles_leaves(suite):
    _assert_scenario(suite, "T19")


def test_t20_linked_messages_ignores_kind_and_shares_targets(suite):
    _assert_scenario(suite, "T20")


def test_t21_linked_messages_is_batched(suite):
    _assert_scenario(suite, "T21")


def test_t22_highlights_scopes_by_board_with_default_ordering(suite):
    _assert_scenario(suite, "T22")


def test_t23_highlights_honours_min_endorsements(suite):
    _assert_scenario(suite, "T23")


def test_t24_highlights_merges_several_boards(suite):
    _assert_scenario(suite, "T24")


def test_t25_highlights_attaches_endorsement_count_metadata(suite):
    _assert_scenario(suite, "T25")


def test_t26_highlights_honours_a_query_filter(suite):
    _assert_scenario(suite, "T26")


def test_t27_highlights_honours_a_query_sort(suite):
    _assert_scenario(suite, "T27")


def test_t28_highlights_honours_limit_and_offset(suite):
    _assert_scenario(suite, "T28")


def test_t29_highlights_code_interface_runs_the_action_once(suite):
    _assert_scenario(suite, "T29")


def test_t30_fork_copies_the_source_subtree(suite):
    _assert_scenario(suite, "T30")


def test_t31_fork_renumbers_positions_by_position_order(suite):
    _assert_scenario(suite, "T31")


def test_t32_fork_records_a_single_fork_of_link(suite):
    _assert_scenario(suite, "T32")


def test_t33_fork_rejects_an_unknown_source_message(suite):
    _assert_scenario(suite, "T33")


def test_t34_fork_rejects_a_locked_source_thread(suite):
    _assert_scenario(suite, "T34")


def test_t35_fork_code_interface_runs_the_action_once(suite):
    _assert_scenario(suite, "T35")
