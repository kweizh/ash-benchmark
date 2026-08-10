"""Final-state verification for the ash_keyset_pagination_feed_api task.

The whole behavioural contract is exercised by a single self-contained ExUnit
suite that is written to /tmp at verify time and executed with `mix run` inside
the project. Each ExUnit scenario emits one machine-readable line, and each
pytest function below reports on exactly one scenario.
"""

import base64
import os
import subprocess
from typing import Any, Dict, Tuple

import pytest

PROJECT_DIR = "/home/user/feedapi"
SUITE_PATH = "/tmp/harbor_feed_pagination_suite.exs"
MARKER = "@@HARBOR@@"

SUITE_EXS = r'''
defmodule HarborFormatter do
  @moduledoc false
  use GenServer

  def init(_opts), do: {:ok, %{}}

  def handle_cast({:test_finished, test}, state) do
    {status, detail} =
      case test.state do
        nil ->
          {"pass", ""}

        {:excluded, _} ->
          {"skip", ""}

        {:skipped, _} ->
          {"skip", ""}

        {:invalid, _} ->
          {"fail", "test invalid (setup failed)"}

        {:failed, failures} ->
          {"fail",
           ExUnit.Formatter.format_test_failure(test, failures, 1, 160, fn _kind, msg -> msg end)}
      end

    IO.puts(
      "@@HARBOR@@" <> to_string(test.name) <> "@@" <> status <> "@@" <> Base.encode64(detail)
    )

    {:noreply, state}
  end

  def handle_cast(_event, state), do: {:noreply, state}
end

ExUnit.start(autorun: false, formatters: [HarborFormatter], seed: 0, colors: [enabled: false])

defmodule Fixture do
  @moduledoc false
  @base ~U[2026-03-01 00:00:00.000000Z]

  def base, do: @base

  def activities do
    for i <- 1..40 do
      %{
        i: i,
        id: "a" <> String.pad_leading(Integer.to_string(i), 2, "0"),
        body: "activity " <> Integer.to_string(i),
        kind: Enum.at([:post, :repost, :reply], rem(i, 3)),
        visibility: if(rem(i, 4) == 0, do: :followers, else: :public),
        score: rem(i, 5),
        published_at: DateTime.add(@base, -i * 3600, :second),
        author_id: if(rem(i, 2) == 1, do: "u_ada", else: "u_bob"),
        reaction_count: rem(i, 3)
      }
    end
  end

  def timeline, do: Module.concat([Feed, Timeline])

  def seed! do
    for author <- [
          %{id: "u_ada", handle: "ada"},
          %{id: "u_bob", handle: "bob"},
          %{id: "u_cyd", handle: "cyd"}
        ] do
      timeline().create_author!(author)
    end

    for activity <- activities() do
      timeline().publish_activity!(
        Map.take(activity, [
          :id,
          :body,
          :kind,
          :visibility,
          :score,
          :published_at,
          :author_id
        ])
      )

      for j <- 1..activity.reaction_count//1 do
        timeline().create_reaction!(%{
          id: "r" <> Integer.to_string(activity.i) <> "_" <> Integer.to_string(j),
          kind: :like,
          activity_id: activity.id
        })
      end
    end

    :ok
  end

  def feed_ids, do: Enum.map(activities(), & &1.id)

  def public_ids do
    activities() |> Enum.filter(&(&1.visibility == :public)) |> Enum.map(& &1.id)
  end

  def author_ids(author_id) do
    activities() |> Enum.filter(&(&1.author_id == author_id)) |> Enum.map(& &1.id)
  end

  def hot_key(a), do: {-a.score, -a.reaction_count, a.id}

  def hot_sorted(list \\ nil), do: Enum.sort_by(list || activities(), &hot_key/1)

  def hot_ids(list \\ nil), do: hot_sorted(list) |> Enum.map(& &1.id)

  def heat(a), do: a.score * 10 + a.reaction_count

  def heat_key(a), do: {-heat(a), a.id}

  def heat_ids, do: activities() |> Enum.sort_by(&heat_key/1) |> Enum.map(& &1.id)
end

defmodule FeedPaginationTest do
  use ExUnit.Case, async: false

  setup do
    Fixture.seed!()
    :ok
  end

  defp timeline, do: Module.concat([Feed, Timeline])
  defp api, do: Module.concat([Feed, Api])
  defp cursor_mod, do: Module.concat([Feed, Cursor])
  defp activity_mod, do: Module.concat([Feed, Timeline, Activity])

  defp ids(%{results: results}), do: Enum.map(results, & &1.id)
  defp ids(%{items: items}), do: Enum.map(items, & &1.id)
  defp ids(list) when is_list(list), do: Enum.map(list, & &1.id)

  defp keyset(record), do: record.__metadata__[:keyset]
  defp last_keyset(page), do: page |> Map.fetch!(:results) |> List.last() |> keyset()
  defp first_keyset(page), do: page |> Map.fetch!(:results) |> List.first() |> keyset()

  defp pagination(action_name),
    do: Ash.Resource.Info.action(activity_mod(), action_name).pagination

  defp error_structs({:error, %Ash.Error.Invalid{errors: errors}}), do: errors
  defp error_structs(other), do: flunk("expected {:error, %Ash.Error.Invalid{}}, got #{inspect(other)}")

  # ---------------------------------------------------------------- DSL contract

  test "T01 the :feed action declares the required keyset pagination contract" do
    p = pagination(:feed)
    assert p.keyset? == true
    assert p.offset? == false
    assert p.required? == true
    assert p.default_limit == 5
    assert p.max_page_size == 25
    assert p.countable == true
  end

  test "T02 the remaining feed actions declare their own pagination contracts" do
    offset = pagination(:feed_offset)
    assert offset.offset? == true
    assert offset.keyset? == false
    assert offset.required? == true
    assert offset.default_limit == 5
    assert offset.max_page_size == 25
    assert offset.countable == :by_default

    assert pagination(:author_feed).max_page_size == 10
    assert pagination(:author_feed).default_limit == 5
    assert pagination(:public_feed).default_limit == 4
    assert pagination(:hot_feed).default_limit == 3
    assert pagination(:heat_feed).default_limit == 3
    assert pagination(:strict_feed).default_limit == nil
    assert pagination(:strict_feed).required? == true
    assert pagination(:uncounted_feed).countable == false
    assert pagination(:uncounted_feed).default_limit == 5

    flexible = pagination(:flexible_feed)
    assert flexible.keyset? == true
    assert flexible.offset? == true
    assert flexible.required? == false
    assert flexible.default_limit == 5
  end

  test "T03 the first keyset page has the documented struct and metadata" do
    page = timeline().feed!(page: [limit: 5])

    assert page.__struct__ == Ash.Page.Keyset
    assert ids(page) == ["a01", "a02", "a03", "a04", "a05"]
    assert page.count == nil
    assert page.more? == true
    assert page.limit == 5
    assert page.before == nil
    assert page.after == nil
    assert Enum.all?(page.results, &is_binary(keyset(&1)))
  end

  test "T04 a keyset page can carry a full count" do
    assert timeline().feed!(page: [limit: 5, count: true]).count == 40
  end

  test "T05 the action's default limit applies when the caller omits one" do
    page = timeline().feed!(page: [count: true])
    assert length(page.results) == 5
    assert ids(page) == ["a01", "a02", "a03", "a04", "a05"]
    assert page.count == 40
  end

  test "T06 forward keyset chaining walks disjoint windows" do
    p1 = timeline().feed!(page: [limit: 5])
    p2 = timeline().feed!(page: [limit: 5, after: last_keyset(p1)])
    p3 = timeline().feed!(page: [limit: 5, after: last_keyset(p2)])

    assert ids(p1) == ["a01", "a02", "a03", "a04", "a05"]
    assert ids(p2) == ["a06", "a07", "a08", "a09", "a10"]
    assert ids(p3) == ["a11", "a12", "a13", "a14", "a15"]
    assert Enum.all?([p1, p2, p3], & &1.more?)
    assert ids(p1) ++ ids(p2) ++ ids(p3) == Enum.take(Fixture.feed_ids(), 15)
  end

  test "T07 backward keyset chaining reproduces the previous windows exactly" do
    p1 = timeline().feed!(page: [limit: 5])
    p2 = timeline().feed!(page: [limit: 5, after: last_keyset(p1)])
    p3 = timeline().feed!(page: [limit: 5, after: last_keyset(p2)])

    back2 = timeline().feed!(page: [limit: 5, before: first_keyset(p3)])
    assert ids(back2) == ids(p2)
    assert back2.more? == true

    back1 = timeline().feed!(page: [limit: 5, before: first_keyset(back2)])
    assert ids(back1) == ids(p1)
    assert back1.more? == false
    assert is_binary(back1.before)
    assert back1.after == nil
  end

  test "T08 Ash.page/2 continues, rewinds, replays and restarts a keyset page" do
    p1 = timeline().feed!(page: [limit: 5])

    assert {:ok, next} = Ash.page(p1, :next)
    assert ids(next) == ["a06", "a07", "a08", "a09", "a10"]

    assert {:ok, prev} = Ash.page(next, :prev)
    assert ids(prev) == ["a01", "a02", "a03", "a04", "a05"]

    assert {:ok, same} = Ash.page(next, :self)
    assert ids(same) == ids(next)

    assert {:ok, first} = Ash.page(next, :first)
    assert ids(first) == ["a01", "a02", "a03", "a04", "a05"]

    assert Ash.page(next, 2) ==
             {:error, "Cannot seek to a specific page with keyset based pagination"}
  end

  test "T09 continuing past the end of a keyset feed yields an empty page" do
    p1 = timeline().feed!(page: [limit: 25])
    assert length(p1.results) == 25

    p2 = timeline().feed!(page: [limit: 25, after: last_keyset(p1)])
    assert ids(p2) == Enum.drop(Fixture.feed_ids(), 25)
    assert p2.more? == false

    assert {:ok, empty} = Ash.page(p2, :next)
    assert empty.__struct__ == Ash.Page.Keyset
    assert empty.results == []
    assert empty.more? == false
  end

  test "T10 the offset feed reports offset, limit, more? and a default count" do
    page = timeline().feed_offset!(page: [limit: 5, offset: 10])

    assert page.__struct__ == Ash.Page.Offset
    assert ids(page) == ["a11", "a12", "a13", "a14", "a15"]
    assert page.offset == 10
    assert page.limit == 5
    assert page.more? == true
    assert page.count == 40

    assert timeline().feed_offset!(page: [limit: 5, count: false]).count == nil
    assert timeline().feed_offset!(page: [limit: 5]).offset == 0
  end

  test "T11 Ash.page/2 seeks an offset page by :last and by page number" do
    page = timeline().feed_offset!(page: [limit: 5, offset: 0])

    assert {:ok, last} = Ash.page(page, :last)
    assert ids(last) == ["a36", "a37", "a38", "a39", "a40"]

    assert {:ok, third} = Ash.page(page, 3)
    assert ids(third) == ["a11", "a12", "a13", "a14", "a15"]
    assert third.offset == 10
  end

  test "T12 the maximum page size caps an over-large limit on :feed" do
    page = timeline().feed!(page: [limit: 1000])

    assert length(page.results) == 26
    assert List.last(page.results).id == "a26"
    assert page.more? == false
    assert page.limit == 1000
  end

  test "T13 :author_feed filters by its argument and caps at its own maximum page size" do
    assert length(timeline().author_feed!("u_ada", page: [limit: 50]).results) == 11

    page = timeline().author_feed!("u_ada", page: [limit: 5, count: true])
    assert ids(page) == ["a01", "a03", "a05", "a07", "a09"]
    assert page.count == 20
  end

  test "T14 disabling pagination on a required action is refused" do
    errors = error_structs(timeline().feed(page: false))
    assert Enum.any?(errors, &match?(%Ash.Error.Invalid.PaginationRequired{}, &1))
  end

  test "T15 an action without a default limit demands one" do
    errors = error_structs(timeline().strict_feed())
    assert Enum.any?(errors, &match?(%Ash.Error.Invalid.LimitRequired{}, &1))

    assert ids(timeline().strict_feed!(page: [limit: 6])) ==
             ["a01", "a02", "a03", "a04", "a05", "a06"]
  end

  test "T16 asking a non-countable action for a count is refused" do
    errors = error_structs(timeline().uncounted_feed(page: [limit: 3, count: true]))

    assert Enum.any?(errors, fn error ->
             match?(
               %Ash.Error.Invalid.NonCountableAction{action: :uncounted_feed},
               error
             ) and error.resource == activity_mod()
           end)

    assert timeline().uncounted_feed!(page: [limit: 3]).count == nil
  end

  test "T17 the dual-mode action is optional and switches page type on demand" do
    unpaged = timeline().flexible_feed!(page: false)
    assert is_list(unpaged)
    assert length(unpaged) == 40

    default = timeline().flexible_feed!()
    assert is_list(default)
    assert length(default) == 40

    offset_page = timeline().flexible_feed!(page: [limit: 3])
    assert offset_page.__struct__ == Ash.Page.Offset
    assert ids(offset_page) == ["a01", "a02", "a03"]

    keyset_page =
      timeline().flexible_feed!(page: [limit: 3, after: last_keyset(offset_page)])

    assert keyset_page.__struct__ == Ash.Page.Keyset
    assert ids(keyset_page) == ["a04", "a05", "a06"]
  end

  test "T18 a malformed keyset is rejected with Ash's keyset error" do
    errors = error_structs(timeline().feed(page: [limit: 3, after: "!!!nope!!!"]))

    assert Enum.any?(errors, fn error ->
             match?(%Ash.Error.Page.InvalidKeyset{value: "!!!nope!!!", key: :after}, error)
           end)

    wrong_arity = Base.encode64(:erlang.term_to_binary([1]))
    errors = error_structs(timeline().feed(page: [limit: 3, after: wrong_arity]))
    assert Enum.any?(errors, &match?(%Ash.Error.Page.InvalidKeyset{}, &1))
  end

  test "T19 :public_feed filters and counts only public activities" do
    page = timeline().public_feed!(page: [limit: 4, count: true])
    assert ids(page) == ["a01", "a02", "a03", "a05"]
    assert page.count == 30

    collected = collect_keyset(:public_feed, [], 4)
    assert collected == Fixture.public_ids()
  end

  test "T20 :hot_feed orders by score, then reaction count, then id" do
    page = timeline().hot_feed!(page: [limit: 3])
    assert ids(page) == Enum.take(Fixture.hot_ids(), 3)

    by_id = Map.new(Fixture.activities(), &{&1.id, &1})

    for record <- page.results do
      fixture = Map.fetch!(by_id, record.id)

      decoded =
        record
        |> keyset()
        |> Base.decode64!()
        |> :erlang.binary_to_term([:safe])

      assert decoded == [fixture.score, fixture.reaction_count, fixture.id]
    end
  end

  test "T21 walking :hot_feed by keyset visits every activity exactly once in hot order" do
    collected = collect_keyset(:hot_feed, [], 3)
    assert collected == Fixture.hot_ids()
    assert length(Enum.uniq(collected)) == 40
  end

  test "T22 walking :heat_feed by keyset visits every activity exactly once in heat order" do
    collected = collect_keyset(:heat_feed, [], 3)
    assert collected == Fixture.heat_ids()
    assert length(Enum.uniq(collected)) == 40
  end

  test "T23 the aggregate, calculation and relationship load on a page" do
    page = timeline().feed!(page: [limit: 10], load: [:author, :reaction_count, :heat])
    by_id = Map.new(page.results, &{&1.id, &1})

    a06 = Map.fetch!(by_id, "a06")
    assert a06.reaction_count == 0
    assert a06.heat == 10

    a08 = Map.fetch!(by_id, "a08")
    assert a08.reaction_count == 2
    assert a08.heat == 32

    assert Map.fetch!(by_id, "a01").author.handle == "ada"
    assert Map.fetch!(by_id, "a02").author.handle == "bob"
  end

  # ---------------------------------------------------------------- Feed.Api

  test "T24 Feed.Api.fetch/2 returns the documented envelope for the first window" do
    assert {:ok, window} = api().fetch(:feed)

    assert Enum.sort(Map.keys(window)) ==
             [:has_next, :has_prev, :items, :next_cursor, :prev_cursor, :total]

    assert ids(window) == ["a01", "a02", "a03", "a04", "a05"]
    assert window.total == 40
    assert window.has_prev == false
    assert window.prev_cursor == nil
    assert window.has_next == true
    assert is_binary(window.next_cursor)

    for item <- window.items do
      assert item.__struct__ == activity_mod()
      assert item.author.__struct__ == Module.concat([Feed, Timeline, Author])
      assert is_integer(item.reaction_count)
      assert is_integer(item.heat)
    end
  end

  test "T25 the cursor codec round-trips and is deterministic and opaque" do
    payloads = [
      %{feed: :feed, direction: :next, keyset: "AAAA"},
      %{feed: :author_feed, direction: :prev, keyset: "!!!nope!!!"}
    ]

    for payload <- payloads do
      encoded = cursor_mod().encode(payload)
      assert is_binary(encoded)
      assert Regex.match?(~r/\A[A-Za-z0-9_-]+\z/, encoded)
      assert cursor_mod().encode(payload) == encoded
      assert cursor_mod().decode(encoded) == {:ok, payload}
    end
  end

  test "T26 the cursor codec rejects corrupt and forged cursors" do
    valid = cursor_mod().encode(%{feed: :feed, direction: :next, keyset: "AAAA"})
    truncated = String.slice(valid, 0..-2//1)

    original = String.at(valid, 2)
    replacement = if original == "Z", do: "Y", else: "Z"
    tampered = String.slice(valid, 0..1//1) <> replacement <> String.slice(valid, 3..-1//1)

    forged =
      Base.url_encode64(
        Jason.encode!(%{"feed" => "feed", "direction" => "next", "keyset" => "AAAA"}),
        padding: false
      )

    vectors = [
      "",
      "not a cursor",
      "AAAA",
      Base.url_encode64("{}", padding: false),
      forged,
      truncated,
      tampered
    ]

    for vector <- vectors do
      assert cursor_mod().decode(vector) == {:error, :invalid_cursor},
             "expected #{inspect(vector)} to be rejected"
    end
  end

  test "T27 forward cursor paging through Feed.Api matches the raw keyset chain" do
    assert {:ok, w1} = api().fetch(:feed, limit: 5)
    assert {:ok, w2} = api().fetch(:feed, limit: 5, cursor: w1.next_cursor)
    assert {:ok, w3} = api().fetch(:feed, limit: 5, cursor: w2.next_cursor)

    assert ids(w1) == ["a01", "a02", "a03", "a04", "a05"]
    assert ids(w2) == ["a06", "a07", "a08", "a09", "a10"]
    assert ids(w3) == ["a11", "a12", "a13", "a14", "a15"]

    assert w1.has_prev == false
    assert w2.has_prev == true
    assert w3.has_prev == true
    assert Enum.all?([w1, w2, w3], &(&1.total == 40))
    assert Enum.all?([w1, w2, w3], &(&1.has_next == true))
  end

  test "T28 backward cursor paging through Feed.Api returns the reversed windows" do
    assert {:ok, w1} = api().fetch(:feed, limit: 5)
    assert {:ok, w2} = api().fetch(:feed, limit: 5, cursor: w1.next_cursor)
    assert {:ok, w3} = api().fetch(:feed, limit: 5, cursor: w2.next_cursor)

    assert {:ok, b2} = api().fetch(:feed, limit: 5, cursor: w3.prev_cursor)
    assert ids(b2) == ids(w2)

    assert {:ok, b1} = api().fetch(:feed, limit: 5, cursor: b2.prev_cursor)
    assert ids(b1) == ids(w1)
    assert b1.has_prev == false
    assert b1.prev_cursor == nil
  end

  test "T29 a cursor issued for one feed is refused by another" do
    assert {:ok, window} = api().fetch(:feed, limit: 5)
    assert api().fetch(:public_feed, limit: 4, cursor: window.next_cursor) ==
             {:error, :cursor_feed_mismatch}
  end

  test "T30 cursor failures surface as codec errors or as Ash's keyset error" do
    poisoned = cursor_mod().encode(%{feed: :feed, direction: :next, keyset: "!!!nope!!!"})

    assert {:error, %Ash.Error.Invalid{} = error} = api().fetch(:feed, cursor: poisoned)
    assert Enum.any?(error.errors, &match?(%Ash.Error.Page.InvalidKeyset{}, &1))

    assert api().fetch(:feed, cursor: "garbage") == {:error, :invalid_cursor}
  end

  test "T31 Feed.Api enforces each feed's maximum page size and rejects bad limits" do
    assert api().fetch(:feed, limit: 26) == {:error, {:limit_too_large, 25}}

    assert api().fetch(:author_feed, author_id: "u_ada", limit: 11) ==
             {:error, {:limit_too_large, 10}}

    assert api().fetch(:feed, limit: 0) == {:error, :invalid_limit}
    assert api().fetch(:feed, limit: "5") == {:error, :invalid_limit}

    assert {:ok, window} = api().fetch(:feed, limit: 25)
    assert length(window.items) == 25
  end

  test "T32 Feed.Api validates the feed name and the author argument" do
    assert api().fetch(:author_feed) == {:error, :author_id_required}
    assert api().fetch(:nope) == {:error, {:unknown_feed, :nope}}

    assert {:ok, window} = api().fetch(:author_feed, author_id: "u_bob", limit: 4)
    assert ids(window) == ["a02", "a04", "a06", "a08"]
    assert window.total == 20
  end

  test "T33 walking the whole feed forwards terminates with exact totals" do
    assert {:ok, walked} = api().walk(:feed, limit: 3)

    assert length(walked.pages) == 14
    assert List.flatten(walked.pages) == Fixture.feed_ids()
    assert length(Enum.uniq(List.flatten(walked.pages))) == 40
    assert length(List.last(walked.pages)) == 1
    assert walked.total == 40
  end

  test "T34 walking a filtered feed and an empty feed" do
    assert {:ok, public} = api().walk(:public_feed, limit: 4)
    assert length(public.pages) == 8
    assert List.flatten(public.pages) == Fixture.public_ids()
    assert public.total == 30

    assert {:ok, empty} = api().walk(:author_feed, author_id: "u_cyd", limit: 5)
    assert empty == %{pages: [[]], total: 0}
  end

  test "T35 walking backwards visits exactly the reversed windows" do
    for {feed, opts} <- [{:feed, [limit: 3]}, {:public_feed, [limit: 4]}, {:hot_feed, [limit: 7]}] do
      assert {:ok, forward} = api().walk(feed, opts)
      assert {:ok, backward} = api().walk_back(feed, opts)

      assert backward.pages == Enum.reverse(forward.pages),
             "walk_back/2 did not mirror walk/2 for #{inspect(feed)}"

      assert backward.total == forward.total
    end
  end

  # ------------------------------------------------- mutation between pages

  test "T36 inserting newer activities between pages neither duplicates nor skips" do
    assert {:ok, w1} = api().fetch(:feed, limit: 5)
    assert ids(w1) == ["a01", "a02", "a03", "a04", "a05"]

    for i <- 1..3 do
      timeline().publish_activity!(%{
        id: "z0" <> Integer.to_string(i),
        body: "inserted",
        kind: :post,
        visibility: :public,
        score: 1,
        published_at: DateTime.add(Fixture.base(), i * 3600, :second),
        author_id: "u_ada"
      })
    end

    assert {:ok, w2} = api().fetch(:feed, limit: 5, cursor: w1.next_cursor)
    assert ids(w2) == ["a06", "a07", "a08", "a09", "a10"]
    assert w2.total == 43
    assert MapSet.disjoint?(MapSet.new(ids(w1)), MapSet.new(ids(w2)))
  end

  test "T37 offset paging over the same insertion repeats rows" do
    before = timeline().feed_offset!(page: [limit: 5])
    assert ids(before) == ["a01", "a02", "a03", "a04", "a05"]

    for i <- 1..3 do
      timeline().publish_activity!(%{
        id: "z0" <> Integer.to_string(i),
        body: "inserted",
        kind: :post,
        visibility: :public,
        score: 1,
        published_at: DateTime.add(Fixture.base(), i * 3600, :second),
        author_id: "u_ada"
      })
    end

    second = timeline().feed_offset!(page: [limit: 5, offset: 5])
    assert ids(second) == ["a03", "a04", "a05", "a06", "a07"]

    overlap =
      MapSet.intersection(MapSet.new(ids(before)), MapSet.new(ids(second))) |> Enum.sort()

    assert overlap == ["a03", "a04", "a05"]
  end

  test "T38 deleting activities between pages does not skip survivors" do
    assert {:ok, w1} = api().fetch(:feed, limit: 5)

    for id <- ["a03", "a07"] do
      activity_mod() |> Ash.get!(id) |> timeline().destroy_activity!()
    end

    assert {:ok, w2} = api().fetch(:feed, limit: 5, cursor: w1.next_cursor)
    assert ids(w2) == ["a06", "a08", "a09", "a10", "a11"]
    assert w2.total == 38
  end

  test "T39 re-scoring between pages keeps the keyset window anchored to the data" do
    assert {:ok, w1} = api().fetch(:hot_feed, limit: 4)
    assert ids(w1) == Enum.take(Fixture.hot_ids(), 4)

    target = Enum.at(Fixture.hot_sorted(), 9)
    activity_mod() |> Ash.get!(target.id) |> timeline().rescore_activity!(%{score: 0})

    mutated =
      Enum.map(Fixture.activities(), fn a ->
        if a.id == target.id, do: %{a | score: 0}, else: a
      end)

    last = List.last(w1.items)
    boundary = {-last.score, -last.reaction_count, last.id}

    expected =
      mutated
      |> Fixture.hot_sorted()
      |> Enum.filter(&(Fixture.hot_key(&1) > boundary))
      |> Enum.take(4)
      |> Enum.map(& &1.id)

    assert {:ok, w2} = api().fetch(:hot_feed, limit: 4, cursor: w1.next_cursor)
    assert ids(w2) == expected
    assert MapSet.disjoint?(MapSet.new(ids(w1)), MapSet.new(ids(w2)))
  end

  test "T40 the reported total stays filtered while paging a filtered feed" do
    public = MapSet.new(Fixture.public_ids())

    windows =
      Enum.reduce(1..8, [], fn
        1, [] ->
          {:ok, first} = api().fetch(:public_feed, limit: 4)
          [first]

        _, [previous | _] = acc ->
          case previous.next_cursor do
            nil ->
              acc

            cursor ->
              {:ok, window} = api().fetch(:public_feed, limit: 4, cursor: cursor)
              [window | acc]
          end
      end)

    assert length(windows) == 8

    for window <- windows do
      assert window.total == 30
      assert Enum.all?(window.items, &MapSet.member?(public, &1.id))
      assert Enum.all?(window.items, &(&1.visibility == :public))
    end
  end

  # ---------------------------------------------------------------- helpers

  defp collect_keyset(action, acc, limit, after_keyset \\ nil) do
    page_opts =
      if after_keyset, do: [limit: limit, after: after_keyset], else: [limit: limit]

    page = apply(timeline(), :"#{action}!", [[page: page_opts]])

    case page.results do
      [] -> Enum.reverse(acc) |> List.flatten()
      results -> collect_keyset(action, [ids(page) | acc], limit, keyset(List.last(results)))
    end
  end
end

ExUnit.run()
'''


def _run_suite() -> Dict[str, Any]:
    with open(SUITE_PATH, "w") as handle:
        handle.write(SUITE_EXS.lstrip("\n"))

    env = dict(os.environ)
    env["MIX_ENV"] = "dev"
    env["HEX_OFFLINE"] = "1"

    compiled = subprocess.run(
        ["mix", "compile"],
        cwd=PROJECT_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=1800,
    )
    executed = subprocess.run(
        ["mix", "run", SUITE_PATH],
        cwd=PROJECT_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=1800,
    )

    results: Dict[str, Tuple[str, str]] = {}
    for line in executed.stdout.splitlines():
        if not line.startswith(MARKER):
            continue
        parts = line.split("@@")
        if len(parts) < 5:
            continue
        name = parts[2]
        status = parts[3]
        try:
            detail = base64.b64decode(parts[4]).decode("utf-8", "replace")
        except Exception:
            detail = parts[4]
        results[name] = (status, detail)

    return {"results": results, "compiled": compiled, "executed": executed}


@pytest.fixture(scope="session")
def suite() -> Dict[str, Any]:
    return _run_suite()


def _diagnostics(suite: Dict[str, Any]) -> str:
    compiled = suite["compiled"]
    executed = suite["executed"]
    return (
        f"`mix compile` exit={compiled.returncode}\n"
        f"--- compile stdout (tail) ---\n{compiled.stdout[-4000:]}\n"
        f"--- compile stderr (tail) ---\n{compiled.stderr[-4000:]}\n"
        f"`mix run` exit={executed.returncode}\n"
        f"--- run stdout (tail) ---\n{executed.stdout[-6000:]}\n"
        f"--- run stderr (tail) ---\n{executed.stderr[-6000:]}"
    )


def _scenario(suite: Dict[str, Any], scenario_id: str) -> None:
    results = suite["results"]
    if not results:
        pytest.fail(
            "The ExUnit contract suite produced no results at all, which normally means "
            "the project failed to compile or the script crashed before running.\n"
            + _diagnostics(suite)
        )

    prefix = f"test {scenario_id} "
    matches = [name for name in results if name.startswith(prefix)]
    assert matches, (
        f"Scenario {scenario_id} did not run. Known scenarios: {sorted(results)}\n"
        + _diagnostics(suite)
    )

    status, detail = results[matches[0]]
    assert status == "pass", f"Scenario {scenario_id} ({matches[0]}) failed:\n{detail}"


def test_project_compiles(suite: Dict[str, Any]) -> None:
    assert suite["compiled"].returncode == 0, (
        "`mix compile` failed for the solved project.\n" + _diagnostics(suite)
    )


def test_contract_suite_ran_completely(suite: Dict[str, Any]) -> None:
    assert len(suite["results"]) == 40, (
        f"Expected 40 contract scenarios to run, saw {len(suite['results'])}.\n"
        + _diagnostics(suite)
    )


def test_t01_feed_action_declares_keyset_pagination_contract(suite: Dict[str, Any]) -> None:
    _scenario(suite, "T01")


def test_t02_other_feed_actions_declare_their_pagination_contracts(suite: Dict[str, Any]) -> None:
    _scenario(suite, "T02")


def test_t03_first_keyset_page_struct_and_metadata(suite: Dict[str, Any]) -> None:
    _scenario(suite, "T03")


def test_t04_keyset_page_carries_full_count(suite: Dict[str, Any]) -> None:
    _scenario(suite, "T04")


def test_t05_default_limit_applies_when_omitted(suite: Dict[str, Any]) -> None:
    _scenario(suite, "T05")


def test_t06_forward_keyset_chaining_walks_disjoint_windows(suite: Dict[str, Any]) -> None:
    _scenario(suite, "T06")


def test_t07_backward_keyset_chaining_reproduces_previous_windows(suite: Dict[str, Any]) -> None:
    _scenario(suite, "T07")


def test_t08_ash_page_continues_rewinds_replays_restarts(suite: Dict[str, Any]) -> None:
    _scenario(suite, "T08")


def test_t09_continuing_past_end_yields_empty_page(suite: Dict[str, Any]) -> None:
    _scenario(suite, "T09")


def test_t10_offset_feed_reports_offset_limit_more_and_default_count(suite: Dict[str, Any]) -> None:
    _scenario(suite, "T10")


def test_t11_ash_page_seeks_offset_page_by_last_and_number(suite: Dict[str, Any]) -> None:
    _scenario(suite, "T11")


def test_t12_max_page_size_caps_over_large_limit(suite: Dict[str, Any]) -> None:
    _scenario(suite, "T12")


def test_t13_author_feed_filters_and_caps_at_own_max_page_size(suite: Dict[str, Any]) -> None:
    _scenario(suite, "T13")


def test_t14_disabling_pagination_on_required_action_is_refused(suite: Dict[str, Any]) -> None:
    _scenario(suite, "T14")


def test_t15_action_without_default_limit_demands_one(suite: Dict[str, Any]) -> None:
    _scenario(suite, "T15")


def test_t16_non_countable_action_refuses_count(suite: Dict[str, Any]) -> None:
    _scenario(suite, "T16")


def test_t17_dual_mode_action_is_optional_and_switches_page_type(suite: Dict[str, Any]) -> None:
    _scenario(suite, "T17")


def test_t18_malformed_keyset_is_rejected(suite: Dict[str, Any]) -> None:
    _scenario(suite, "T18")


def test_t19_public_feed_filters_and_counts_public_only(suite: Dict[str, Any]) -> None:
    _scenario(suite, "T19")


def test_t20_hot_feed_orders_by_score_then_reactions_then_id(suite: Dict[str, Any]) -> None:
    _scenario(suite, "T20")


def test_t21_hot_feed_keyset_walk_visits_every_activity_once(suite: Dict[str, Any]) -> None:
    _scenario(suite, "T21")


def test_t22_heat_feed_keyset_walk_visits_every_activity_once(suite: Dict[str, Any]) -> None:
    _scenario(suite, "T22")


def test_t23_aggregate_calculation_and_relationship_load_on_page(suite: Dict[str, Any]) -> None:
    _scenario(suite, "T23")


def test_t24_api_fetch_returns_documented_envelope(suite: Dict[str, Any]) -> None:
    _scenario(suite, "T24")


def test_t25_cursor_codec_round_trips_and_is_opaque(suite: Dict[str, Any]) -> None:
    _scenario(suite, "T25")


def test_t26_cursor_codec_rejects_corrupt_and_forged_cursors(suite: Dict[str, Any]) -> None:
    _scenario(suite, "T26")


def test_t27_api_forward_cursor_paging_matches_raw_keyset_chain(suite: Dict[str, Any]) -> None:
    _scenario(suite, "T27")


def test_t28_api_backward_cursor_paging_returns_reversed_windows(suite: Dict[str, Any]) -> None:
    _scenario(suite, "T28")


def test_t29_cursor_from_one_feed_is_refused_by_another(suite: Dict[str, Any]) -> None:
    _scenario(suite, "T29")


def test_t30_cursor_failures_surface_as_codec_or_ash_errors(suite: Dict[str, Any]) -> None:
    _scenario(suite, "T30")


def test_t31_api_enforces_max_page_size_and_rejects_bad_limits(suite: Dict[str, Any]) -> None:
    _scenario(suite, "T31")


def test_t32_api_validates_feed_name_and_author_argument(suite: Dict[str, Any]) -> None:
    _scenario(suite, "T32")


def test_t33_forward_walk_terminates_with_exact_totals(suite: Dict[str, Any]) -> None:
    _scenario(suite, "T33")


def test_t34_walk_of_filtered_feed_and_of_empty_feed(suite: Dict[str, Any]) -> None:
    _scenario(suite, "T34")


def test_t35_walk_back_visits_exactly_the_reversed_windows(suite: Dict[str, Any]) -> None:
    _scenario(suite, "T35")


def test_t36_insertion_between_pages_neither_duplicates_nor_skips(suite: Dict[str, Any]) -> None:
    _scenario(suite, "T36")


def test_t37_offset_paging_over_same_insertion_repeats_rows(suite: Dict[str, Any]) -> None:
    _scenario(suite, "T37")


def test_t38_deletion_between_pages_does_not_skip_survivors(suite: Dict[str, Any]) -> None:
    _scenario(suite, "T38")


def test_t39_rescoring_between_pages_keeps_window_anchored(suite: Dict[str, Any]) -> None:
    _scenario(suite, "T39")


def test_t40_reported_total_stays_filtered_while_paging(suite: Dict[str, Any]) -> None:
    _scenario(suite, "T40")
