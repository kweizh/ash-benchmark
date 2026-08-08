"""Final-state verification for the Ash transactional-outbox task.

The behavioural contract is checked by running a self-contained ExUnit suite inside
the executor's project with `mix run`. The suite is written to /tmp at verify time,
so nothing inside the project is touched. Each ExUnit test emits one line of the form

    @@HARBOR@@<test name>@@<pass|fail>@@<base64 encoded failure detail>

which lets pytest report every behaviour as its own test case.
"""

import base64
import os
import subprocess
from typing import Dict, Tuple

import pytest

PROJECT_DIR = "/home/user/outbox"
SUITE_PATH = "/tmp/harbor_outbox_suite.exs"
MARKER = "@@HARBOR@@"

SUITE_SOURCE = r"""
defmodule Harbor.Formatter do
  @moduledoc false
  use GenServer

  def init(_opts), do: {:ok, %{}}

  def handle_cast({:test_finished, %ExUnit.Test{} = test}, state) do
    {status, detail} =
      case test.state do
        nil ->
          {"pass", ""}

        {:excluded, _} ->
          {"pass", ""}

        {:skipped, _} ->
          {"pass", ""}

        {:failed, failures} ->
          {"fail", ExUnit.Formatter.format_test_failure(test, failures, 1, 120, fn _, m -> m end)}

        {:invalid, module} ->
          {"fail", "invalid module #{inspect(module)}"}
      end

    IO.puts("@@HARBOR@@#{test.name}@@#{status}@@#{Base.encode64(detail)}")
    {:noreply, state}
  end

  def handle_cast(_event, state), do: {:noreply, state}
end

# --- warm the ETS tables so lazy table creation never races -------------------
for resource <- [Outbox.Ledger.Account, Outbox.Ledger.Transfer] do
  Ash.read(resource)
end

ExUnit.start(
  autorun: false,
  formatters: [Harbor.Formatter],
  seed: 0,
  max_failures: :infinity,
  timeout: 120_000,
  colors: [enabled: false]
)

defmodule Harbor.OutboxTest do
  use ExUnit.Case, async: false

  @account Outbox.Ledger.Account
  @transfer Outbox.Ledger.Transfer

  defp eventing, do: Module.concat([:Outbox, :Eventing])
  defp event_resource, do: Module.concat([:Outbox, :Eventing, :Event])
  defp dispatcher, do: Module.concat([:Outbox, :Eventing, :Dispatcher])
  defp bulk_ops, do: Module.concat([:Outbox, :Ledger, :BulkOps])

  defp reset!, do: apply(dispatcher(), :reset, [])
  defp flush!, do: apply(dispatcher(), :flush, [])
  defp events, do: apply(eventing(), :list_events!, [])
  defp events_for(type, id), do: apply(eventing(), :events_for!, [type, id])
  defp dead_letters, do: apply(dispatcher(), :dead_letters, [])
  defp replay(after_seq, id), do: apply(eventing(), :replay, [after_seq, id])

  defp subscribe(id, pattern, handler, opts \\ []) do
    apply(dispatcher(), :subscribe, [id, pattern, handler, opts])
  end

  defp unsubscribe(id), do: apply(dispatcher(), :unsubscribe, [id])

  defp open_account(attrs \\ %{}, opts \\ []) do
    params = Map.merge(%{owner_id: "own-1", name: "Main", balance: 0}, attrs)
    Ash.create!(@account, params, [action: :open] ++ opts)
  end

  defp drain_mailbox(acc \\ []) do
    receive do
      msg -> drain_mailbox([msg | acc])
    after
      0 -> Enum.reverse(acc)
    end
  end

  setup do
    reset!()
    drain_mailbox()
    :ok
  end

  # --------------------------------------------------------------------------

  test "T01 dispatcher is supervised by the application" do
    pid = Process.whereis(dispatcher())
    assert is_pid(pid), "Outbox.Eventing.Dispatcher is not a registered process"
    assert Process.alive?(pid)

    children = Supervisor.which_children(Outbox.Supervisor)
    pids = Enum.map(children, fn {_id, child, _type, _mods} -> child end)
    assert pid in pids, "dispatcher is not a child of Outbox.Supervisor"
  end

  test "T02 outbox resource shape" do
    resource = event_resource()

    assert Ash.Resource.Info.data_layer(resource) == Ash.DataLayer.Ets

    expected = [
      sequence: Ash.Type.Integer,
      aggregate_sequence: Ash.Type.Integer,
      topic: Ash.Type.String,
      resource: Ash.Type.String,
      aggregate_type: Ash.Type.String,
      aggregate_id: Ash.Type.String,
      action: Ash.Type.Atom,
      actor_id: Ash.Type.String,
      changes: Ash.Type.Map,
      dedup_key: Ash.Type.String
    ]

    for {name, type} <- expected do
      attribute = Ash.Resource.Info.attribute(resource, name)
      assert attribute, "missing attribute #{name}"
      assert attribute.type == type, "attribute #{name} has type #{inspect(attribute.type)}"
    end

    identity = Ash.Resource.Info.identity(resource, :unique_dedup_key)
    assert identity, "missing identity :unique_dedup_key"
    assert identity.keys == [:dedup_key]

    action = Ash.Resource.Info.action(resource, :replay)
    assert action, "missing :replay action"
    assert action.type == :action, ":replay must be a generic action"

    assert eventing() in Application.get_env(:outbox, :ash_domains, [])
  end

  test "T03 a create is captured with full metadata" do
    account = open_account(%{owner_id: "own-1", name: "Main", balance: 10}, actor: %{id: "user-7"})

    assert [event] = events()
    assert event.sequence == 1
    assert event.aggregate_sequence == 1
    assert event.topic == "ledger.account.open"
    assert event.resource == "Outbox.Ledger.Account"
    assert event.aggregate_type == "account"
    assert event.aggregate_id == account.id
    assert event.action == :open
    assert event.actor_id == "user-7"
    assert event.dedup_key == "account:#{account.id}:open:1"
  end

  test "T04 create diff carries every non-nil public attribute with a nil from" do
    _account = open_account(%{owner_id: "own-1", name: "Main", balance: 10})

    assert [event] = events()

    assert event.changes == %{
             "owner_id" => %{"from" => nil, "to" => "own-1"},
             "name" => %{"from" => nil, "to" => "Main"},
             "balance" => %{"from" => nil, "to" => 10},
             "status" => %{"from" => nil, "to" => "active"}
           }
  end

  test "T05 update diffs contain only the attributes that really changed" do
    account = open_account(%{owner_id: "own-1", name: "Main", balance: 10})
    account = Ash.update!(account, %{name: "Renamed"}, action: :rename)
    account = Ash.update!(account, %{}, action: :freeze)
    _account = Ash.update!(account, %{amount: 5}, action: :deposit)

    assert [_open, rename, freeze, deposit] = events()

    assert rename.changes == %{"name" => %{"from" => "Main", "to" => "Renamed"}}
    assert rename.sequence == 2
    assert rename.aggregate_sequence == 2

    assert freeze.changes == %{"status" => %{"from" => "active", "to" => "frozen"}}
    assert freeze.sequence == 3
    assert freeze.aggregate_sequence == 3

    assert deposit.changes == %{"balance" => %{"from" => 10, "to" => 15}}
    assert deposit.sequence == 4
    assert deposit.aggregate_sequence == 4
  end

  test "T06 a destroy is captured with an empty diff" do
    account = open_account(%{owner_id: "own-1", name: "Main", balance: 10})
    account = Ash.update!(account, %{name: "Renamed"}, action: :rename)
    account = Ash.update!(account, %{}, action: :freeze)
    account = Ash.update!(account, %{amount: 5}, action: :deposit)
    :ok = Ash.destroy!(account, action: :close)

    assert [_open, _rename, _freeze, _deposit, close] = events()
    assert close.action == :close
    assert close.topic == "ledger.account.close"
    assert close.changes == %{}
    assert close.aggregate_sequence == 5
  end

  test "T07 actor_id is nil when the write has no actor" do
    _account = open_account()
    assert [event] = events()
    assert event.actor_id == nil
  end

  test "T08 aggregate counters are independent while the global counter is contiguous" do
    transfer = Ash.create!(@transfer, %{from_account_id: "a", to_account_id: "b", amount: 3}, action: :record)
    _transfer = Ash.update!(transfer, %{}, action: :settle)
    account_a = open_account(%{owner_id: "own-a", name: "A"})
    _account_a = Ash.update!(account_a, %{name: "A2"}, action: :rename)
    account_b = open_account(%{owner_id: "own-b", name: "B"})

    all = events()
    assert length(all) == 5
    assert Enum.map(all, & &1.sequence) == [1, 2, 3, 4, 5]

    assert Enum.map(all, &{&1.topic, &1.aggregate_type, &1.aggregate_sequence}) == [
             {"ledger.transfer.record", "transfer", 1},
             {"ledger.transfer.settle", "transfer", 2},
             {"ledger.account.open", "account", 1},
             {"ledger.account.rename", "account", 2},
             {"ledger.account.open", "account", 1}
           ]

    assert Enum.at(all, 4).aggregate_id == account_b.id
  end

  test "T09 failed writes leave no entry" do
    assert {:error, %Ash.Error.Invalid{}} = Ash.create(@account, %{name: "NoOwner"}, action: :open)
    assert events() == []

    account = open_account(%{owner_id: "own-1", name: "Main", balance: 10})
    assert {:error, %Ash.Error.Invalid{}} = Ash.update(account, %{amount: 99}, action: :withdraw)
    assert length(events()) == 1
  end

  test "T10 notifications can be suppressed for a single call" do
    result =
      Ash.create(@account, %{owner_id: "own-quiet", name: "Quiet"},
        action: :open,
        return_notifications?: true
      )

    assert {:ok, account, notifications} = result
    assert notifications != []
    assert events() == []
    assert Ash.get!(@account, account.id)
  end

  test "T11 batch create emits exactly one entry per created record" do
    inputs =
      for i <- 1..5 do
        %{owner_id: "bulk-#{i}", name: "Bulk #{i}", balance: i}
      end

    assert {:ok, accounts} = apply(bulk_ops(), :open_many, [inputs])
    assert length(accounts) == 5

    all = events()
    assert length(all) == 5
    assert Enum.sort(Enum.map(all, & &1.sequence)) == [1, 2, 3, 4, 5]
    assert Enum.sort(Enum.map(all, & &1.aggregate_id)) == Enum.sort(Enum.map(accounts, & &1.id))
    assert Enum.all?(all, &(&1.aggregate_sequence == 1))
    assert Enum.all?(all, &(&1.action == :open))
    assert Enum.all?(all, &(&1.topic == "ledger.account.open"))

    by_owner = Map.new(all, &{get_in(&1.changes, ["owner_id", "to"]), &1.changes})

    assert by_owner["bulk-3"] == %{
             "owner_id" => %{"from" => nil, "to" => "bulk-3"},
             "name" => %{"from" => nil, "to" => "Bulk 3"},
             "balance" => %{"from" => nil, "to" => 3},
             "status" => %{"from" => nil, "to" => "active"}
           }
  end

  test "T12 batch update emits exactly one entry per updated record" do
    inputs = for i <- 1..5, do: %{owner_id: "bulkup-#{i}", name: "BulkUp #{i}"}
    assert {:ok, accounts} = apply(bulk_ops(), :open_many, [inputs])
    assert {:ok, frozen} = apply(bulk_ops(), :freeze_many, [accounts])
    assert length(frozen) == 5

    all = events()
    assert length(all) == 10

    freezes = Enum.filter(all, &(&1.action == :freeze))
    assert length(freezes) == 5
    assert Enum.sort(Enum.map(freezes, & &1.aggregate_id)) == Enum.sort(Enum.map(accounts, & &1.id))
    assert Enum.all?(freezes, &(&1.aggregate_sequence == 2))
    assert Enum.all?(freezes, &(get_in(&1.changes, ["status", "to"]) == "frozen"))
    assert Enum.all?(frozen, &(&1.status == :frozen))
  end

  test "T28 a batch update issued directly through Ash emits one entry per record" do
    inputs = for i <- 1..4, do: %{owner_id: "direct-#{i}", name: "Direct #{i}"}
    assert {:ok, accounts} = apply(bulk_ops(), :open_many, [inputs])
    reset!()

    result =
      Ash.bulk_update(accounts, :rename, %{name: "Renamed"},
        return_records?: true,
        return_errors?: true,
        notify?: true
      )

    assert result.status == :success
    assert length(result.records || []) == 4

    all = events()
    assert length(all) == 4
    assert Enum.sort(Enum.map(all, & &1.sequence)) == [1, 2, 3, 4]
    assert Enum.sort(Enum.map(all, & &1.aggregate_id)) == Enum.sort(Enum.map(accounts, & &1.id))
    assert Enum.all?(all, &(&1.action == :rename))
    assert Enum.all?(all, &(&1.topic == "ledger.account.rename"))
    assert Enum.all?(all, &(&1.aggregate_sequence == 1))
    assert Enum.all?(all, &(get_in(&1.changes, ["name", "to"]) == "Renamed"))
  end

  test "T13 a partially failing batch only records the rows that succeeded" do
    inputs = [
      %{owner_id: "part-1", name: "Ok 1"},
      %{name: "Broken 1"},
      %{owner_id: "part-2", name: "Ok 2"},
      %{name: "Broken 2"}
    ]

    result =
      Ash.bulk_create(inputs, @account, :open,
        return_records?: true,
        return_errors?: true,
        stop_on_error?: false,
        notify?: true
      )

    created = result.records || []
    assert length(created) == 2

    all = events()
    assert length(all) == 2
    assert Enum.sort(Enum.map(all, & &1.aggregate_id)) == Enum.sort(Enum.map(created, & &1.id))
  end

  test "T14 sync subscribers run inline in the writing process" do
    test_pid = self()

    handler = fn event ->
      send(test_pid, {:got, self(), event.sequence})
      :ok
    end

    assert :ok = subscribe(:sync_sub, "ledger.account.*", handler, mode: :sync)

    _account = open_account()

    assert_received {:got, handler_pid, 1}
    assert handler_pid == test_pid, "a :sync handler must run in the writing process"
  end

  test "T15 async subscribers only run in the dispatcher on drain" do
    test_pid = self()

    handler = fn event ->
      send(test_pid, {:got, self(), event.sequence})
      :ok
    end

    assert :ok = subscribe(:async_sub, "ledger.account.*", handler)

    _account = open_account()

    refute_received {:got, _, _}

    :ok = flush!()

    assert_received {:got, handler_pid, 1}
    assert handler_pid == Process.whereis(dispatcher()), "an :async handler must run in the dispatcher"
  end

  test "T16 topic patterns match with segment precision" do
    test_pid = self()

    transfer =
      Ash.create!(@transfer, %{from_account_id: "a", to_account_id: "b", amount: 1}, action: :record)

    patterns = [
      {:p_exact, "ledger.account.open", ["ledger.account.open"]},
      {:p_tail_star, "ledger.account.*", ["ledger.account.open"]},
      {:p_mid_star, "ledger.*.open", ["ledger.account.open"]},
      {:p_hash, "ledger.#", ["ledger.account.open", "ledger.transfer.settle"]},
      {:p_root_hash, "#", ["ledger.account.open", "ledger.transfer.settle"]},
      {:p_head_star, "*.account.open", ["ledger.account.open"]},
      {:p_all_star, "*.*.*", ["ledger.account.open", "ledger.transfer.settle"]},
      {:p_two_seg_star, "ledger.*", []},
      {:p_two_seg, "ledger.account", []},
      {:p_partial, "ledger.acc*", []},
      {:p_account_hash, "ledger.account.#", ["ledger.account.open"]}
    ]

    for {id, pattern, _expected} <- patterns do
      handler = fn event -> send(test_pid, {:pat, id, event.topic}) && :ok end
      assert :ok = subscribe(id, pattern, handler)
    end

    _account = open_account()
    _transfer = Ash.update!(transfer, %{}, action: :settle)

    :ok = flush!()

    received =
      drain_mailbox()
      |> Enum.reduce(%{}, fn {:pat, id, topic}, acc ->
        Map.update(acc, id, [topic], &(&1 ++ [topic]))
      end)

    for {id, pattern, expected} <- patterns do
      assert Enum.sort(Map.get(received, id, [])) == Enum.sort(expected),
             "pattern #{pattern} selected #{inspect(Map.get(received, id, []))}"
    end
  end

  test "T17 per-aggregate order survives interleaved concurrent writers" do
    account = open_account(%{owner_id: "conc", name: "C0"})
    reset!()
    drain_mailbox()

    test_pid = self()
    handler = fn event -> send(test_pid, {:seen, event.aggregate_sequence}) && :ok end
    assert :ok = subscribe(:watcher, "ledger.account.rename", handler)

    1..4
    |> Task.async_stream(
      fn writer ->
        Enum.each(1..5, fn n ->
          Ash.update!(account, %{name: "w#{writer}-#{n}"}, action: :rename)
        end)
      end,
      max_concurrency: 4,
      timeout: 60_000
    )
    |> Stream.run()

    all = events_for("account", account.id)
    assert length(all) == 20
    assert Enum.map(all, & &1.aggregate_sequence) == Enum.to_list(1..20)
    assert length(Enum.uniq(Enum.map(all, & &1.sequence))) == 20

    :ok = flush!()

    seen = for {:seen, n} <- drain_mailbox(), do: n
    assert seen == Enum.to_list(1..20)
  end

  test "T18 acknowledged deliveries are never repeated" do
    test_pid = self()

    for id <- [:ack_a, :ack_b] do
      handler = fn event -> send(test_pid, {:hit, id, event.sequence}) && :ok end
      assert :ok = subscribe(id, "ledger.account.*", handler)
    end

    _account = open_account()

    :ok = flush!()
    :ok = flush!()
    :ok = flush!()

    hits = drain_mailbox()
    assert Enum.sort(hits) == [{:hit, :ack_a, 1}, {:hit, :ack_b, 1}]
    assert dead_letters() == []
  end

  test "T19 a delivery that fails twice still succeeds on the third attempt" do
    test_pid = self()
    counter = :counters.new(1, [])

    flaky = fn event ->
      :counters.add(counter, 1, 1)
      send(test_pid, {:flaky, event.sequence})

      if :counters.get(counter, 1) < 3 do
        {:error, :not_yet}
      else
        :ok
      end
    end

    healthy_counter = :counters.new(1, [])

    healthy = fn _event ->
      :counters.add(healthy_counter, 1, 1)
      :ok
    end

    assert :ok = subscribe(:flaky, "ledger.account.*", flaky)
    assert :ok = subscribe(:healthy, "ledger.account.*", healthy)

    _account = open_account()

    :ok = flush!()
    :ok = flush!()
    :ok = flush!()
    :ok = flush!()

    assert :counters.get(counter, 1) == 3
    assert :counters.get(healthy_counter, 1) == 1
    assert dead_letters() == []
  end

  test "T20 a delivery is dead-lettered after three failed attempts" do
    counter = :counters.new(1, [])

    doomed = fn _event ->
      :counters.add(counter, 1, 1)
      {:error, :boom}
    end

    assert :ok = subscribe(:doomed, "ledger.account.*", doomed)

    _account = open_account()

    :ok = flush!()
    :ok = flush!()
    :ok = flush!()

    assert :counters.get(counter, 1) == 3

    assert [letter] = dead_letters()

    assert Map.take(letter, [:subscriber_id, :sequence, :attempts, :reason]) == %{
             subscriber_id: :doomed,
             sequence: 1,
             attempts: 3,
             reason: :boom
           }

    :ok = flush!()
    :ok = flush!()

    assert :counters.get(counter, 1) == 3
    assert length(dead_letters()) == 1
  end

  test "T21 a raising handler is contained" do
    test_pid = self()
    pid_before = Process.whereis(dispatcher())

    boomer = fn _event -> raise RuntimeError, "kaboom" end
    sibling = fn event -> send(test_pid, {:sibling, event.sequence}) && :ok end

    assert :ok = subscribe(:boomer, "ledger.account.*", boomer)
    assert :ok = subscribe(:sibling, "ledger.account.*", sibling)

    _account = open_account()

    :ok = flush!()
    :ok = flush!()
    :ok = flush!()

    assert Process.whereis(dispatcher()) == pid_before
    assert Process.alive?(pid_before)

    assert_received {:sibling, 1}
    refute_received {:sibling, _}

    assert [letter] = dead_letters()
    assert letter.subscriber_id == :boomer
    assert letter.reason == {:raised, "kaboom"}
    assert letter.attempts == 3
  end

  test "T22 a sync delivery that fails is retried like an async one" do
    counter = :counters.new(1, [])

    handler = fn _event ->
      :counters.add(counter, 1, 1)
      {:error, :nope}
    end

    assert :ok = subscribe(:sync_fail, "ledger.account.*", handler, mode: :sync)

    account = open_account()
    assert account.id

    assert :counters.get(counter, 1) == 1
    assert dead_letters() == []

    :ok = flush!()
    assert :counters.get(counter, 1) == 2
    assert dead_letters() == []

    :ok = flush!()
    assert :counters.get(counter, 1) == 3

    assert [letter] = dead_letters()
    assert letter.subscriber_id == :sync_fail
    assert letter.attempts == 3
    assert letter.reason == :nope

    :ok = flush!()
    assert :counters.get(counter, 1) == 3
  end

  test "T23 replay re-delivers matching entries in order in the caller process" do
    test_pid = self()

    _transfer =
      Ash.create!(@transfer, %{from_account_id: "a", to_account_id: "b", amount: 1}, action: :record)

    handler = fn event -> send(test_pid, {:replayed, self(), event.sequence}) && :ok end
    assert :ok = subscribe(:replayer, "ledger.account.*", handler)

    account = open_account()
    _account = Ash.update!(account, %{name: "R2"}, action: :rename)

    :ok = flush!()
    drain_mailbox()

    assert {:ok, [2, 3]} = replay(0, :replayer)

    assert [{:replayed, p1, 2}, {:replayed, p2, 3}] = drain_mailbox()
    assert p1 == test_pid
    assert p2 == test_pid

    assert {:ok, [3]} = replay(2, :replayer)
    assert [{:replayed, _, 3}] = drain_mailbox()

    assert {:ok, []} = replay(0, :nobody)
    assert drain_mailbox() == []

    assert dead_letters() == []
    :ok = flush!()
    assert drain_mailbox() == []
  end

  test "T24 subscription bookkeeping" do
    test_pid = self()
    handler = fn event -> send(test_pid, {:x, event.sequence}) && :ok end

    assert :ok = subscribe(:dup, "ledger.#", handler)
    assert {:error, :already_subscribed} = subscribe(:dup, "ledger.#", handler)

    gone = fn event -> send(test_pid, {:gone, event.sequence}) && :ok end
    stay = fn event -> send(test_pid, {:stay, event.sequence}) && :ok end

    assert :ok = subscribe(:gone, "ledger.account.*", gone)
    assert :ok = subscribe(:stay, "ledger.account.*", stay)

    _account = open_account()

    assert :ok = unsubscribe(:gone)
    :ok = flush!()

    assert_received {:stay, 1}
    refute_received {:gone, _}
  end

  test "T25 dedup keys are unique and protected by an identity" do
    account = open_account(%{owner_id: "dk", name: "DK"})
    account = Ash.update!(account, %{name: "DK2"}, action: :rename)
    _account = Ash.update!(account, %{}, action: :freeze)

    inputs = for i <- 1..3, do: %{owner_id: "dk-#{i}", name: "DK #{i}"}
    assert {:ok, _} = apply(bulk_ops(), :open_many, [inputs])

    all = events()
    keys = Enum.map(all, & &1.dedup_key)
    assert length(Enum.uniq(keys)) == length(keys)

    for event <- all do
      expected =
        "#{event.aggregate_type}:#{event.aggregate_id}:#{event.action}:#{event.aggregate_sequence}"

      assert event.dedup_key == expected
    end

    first = hd(all)

    duplicate =
      Ash.create(event_resource(), %{
        sequence: 999,
        aggregate_sequence: 999,
        topic: first.topic,
        resource: first.resource,
        aggregate_type: first.aggregate_type,
        aggregate_id: first.aggregate_id,
        action: first.action,
        actor_id: nil,
        changes: %{},
        dedup_key: first.dedup_key
      })

    assert {:error, %Ash.Error.Invalid{}} = duplicate
  end

  test "T26 query helpers are ordered and scoped" do
    a = open_account(%{owner_id: "q-a", name: "QA"})
    b = open_account(%{owner_id: "q-b", name: "QB"})
    _a = Ash.update!(a, %{name: "QA2"}, action: :rename)
    _b = Ash.update!(b, %{name: "QB2"}, action: :rename)

    assert Enum.map(events(), & &1.sequence) == [1, 2, 3, 4]

    for_a = events_for("account", a.id)
    assert Enum.map(for_a, & &1.aggregate_sequence) == [1, 2]
    assert Enum.all?(for_a, &(&1.aggregate_id == a.id))

    assert events_for("account", "does-not-exist") == []
  end

  test "T27 reset returns the subsystem to a pristine state" do
    test_pid = self()
    handler = fn _event -> send(test_pid, :boom) && {:error, :boom} end
    assert :ok = subscribe(:resettable, "ledger.#", handler)

    _account = open_account(%{owner_id: "r-1", name: "R1"})
    :ok = flush!()
    :ok = flush!()
    :ok = flush!()

    assert length(events()) == 1
    assert length(dead_letters()) == 1

    :ok = reset!()
    drain_mailbox()

    assert events() == []
    assert dead_letters() == []
    assert :ok = subscribe(:resettable, "ledger.#", fn _ -> :ok end)

    account = open_account(%{owner_id: "r-2", name: "R2"})
    assert [event] = events()
    assert event.sequence == 1
    assert event.aggregate_sequence == 1
    assert event.aggregate_id == account.id
  end
end

ExUnit.run()
"""


def _env() -> Dict[str, str]:
    env = os.environ.copy()
    env.pop("MIX_ENV", None)
    env["HEX_OFFLINE"] = "1"
    env["MIX_QUIET"] = "0"
    return env


@pytest.fixture(scope="session")
def suite_run() -> Tuple[Dict[str, Tuple[str, str]], str]:
    """Compile the project, run the ExUnit suite once and parse its per-test output."""
    with open(SUITE_PATH, "w", encoding="utf-8") as handle:
        handle.write(SUITE_SOURCE.lstrip("\n"))

    compile_result = subprocess.run(
        ["mix", "compile"],
        cwd=PROJECT_DIR,
        capture_output=True,
        text=True,
        timeout=1800,
        env=_env(),
    )
    compile_output = compile_result.stdout + compile_result.stderr

    if compile_result.returncode != 0:
        return {}, "`mix compile` failed:\n" + compile_output

    run_result = subprocess.run(
        ["mix", "run", SUITE_PATH],
        cwd=PROJECT_DIR,
        capture_output=True,
        text=True,
        timeout=1800,
        env=_env(),
    )
    output = compile_output + run_result.stdout + run_result.stderr

    results: Dict[str, Tuple[str, str]] = {}
    for line in run_result.stdout.splitlines():
        line = line.strip()
        if not line.startswith(MARKER):
            continue
        parts = line.split("@@")
        if len(parts) < 5:
            continue
        name, status, encoded = parts[2], parts[3], parts[4]
        try:
            detail = base64.b64decode(encoded).decode("utf-8", errors="replace")
        except Exception:  # pragma: no cover - defensive
            detail = encoded
        results[name] = (status, detail)

    return results, output


def _assert_scenario(
    suite_run: Tuple[Dict[str, Tuple[str, str]], str], scenario_id: str
) -> None:
    results, output = suite_run
    matching = [key for key in results if key.startswith(f"test {scenario_id} ")]
    assert matching, (
        f"The ExUnit suite produced no result for scenario {scenario_id}. "
        f"Last 6000 characters of the run output:\n{output[-6000:]}"
    )
    status, detail = results[matching[0]]
    assert status == "pass", f"Scenario {scenario_id} failed:\n{detail}"


def test_t01_dispatcher_is_supervised_by_the_application(suite_run) -> None:
    """T01: dispatcher is supervised by the application."""
    _assert_scenario(suite_run, "T01")


def test_t02_outbox_resource_shape(suite_run) -> None:
    """T02: outbox resource shape."""
    _assert_scenario(suite_run, "T02")


def test_t03_a_create_is_captured_with_full_metadata(suite_run) -> None:
    """T03: a create is captured with full metadata."""
    _assert_scenario(suite_run, "T03")


def test_t04_create_diff_carries_every_non_nil_public_attribute_with_a_nil_from(suite_run) -> None:
    """T04: create diff carries every non-nil public attribute with a nil from."""
    _assert_scenario(suite_run, "T04")


def test_t05_update_diffs_contain_only_the_attributes_that_really_changed(suite_run) -> None:
    """T05: update diffs contain only the attributes that really changed."""
    _assert_scenario(suite_run, "T05")


def test_t06_a_destroy_is_captured_with_an_empty_diff(suite_run) -> None:
    """T06: a destroy is captured with an empty diff."""
    _assert_scenario(suite_run, "T06")


def test_t07_actor_id_is_nil_when_the_write_has_no_actor(suite_run) -> None:
    """T07: actor_id is nil when the write has no actor."""
    _assert_scenario(suite_run, "T07")


def test_t08_aggregate_counters_are_independent_while_the_global_counter_is_contigu(suite_run) -> None:
    """T08: aggregate counters are independent while the global counter is contiguous."""
    _assert_scenario(suite_run, "T08")


def test_t09_failed_writes_leave_no_entry(suite_run) -> None:
    """T09: failed writes leave no entry."""
    _assert_scenario(suite_run, "T09")


def test_t10_notifications_can_be_suppressed_for_a_single_call(suite_run) -> None:
    """T10: notifications can be suppressed for a single call."""
    _assert_scenario(suite_run, "T10")


def test_t11_batch_create_emits_exactly_one_entry_per_created_record(suite_run) -> None:
    """T11: batch create emits exactly one entry per created record."""
    _assert_scenario(suite_run, "T11")


def test_t12_batch_update_emits_exactly_one_entry_per_updated_record(suite_run) -> None:
    """T12: batch update emits exactly one entry per updated record."""
    _assert_scenario(suite_run, "T12")


def test_t28_a_batch_update_issued_directly_through_ash_emits_one_entry_per_record(suite_run) -> None:
    """T28: a batch update issued directly through Ash emits one entry per record."""
    _assert_scenario(suite_run, "T28")


def test_t13_a_partially_failing_batch_only_records_the_rows_that_succeeded(suite_run) -> None:
    """T13: a partially failing batch only records the rows that succeeded."""
    _assert_scenario(suite_run, "T13")


def test_t14_sync_subscribers_run_inline_in_the_writing_process(suite_run) -> None:
    """T14: sync subscribers run inline in the writing process."""
    _assert_scenario(suite_run, "T14")


def test_t15_async_subscribers_only_run_in_the_dispatcher_on_drain(suite_run) -> None:
    """T15: async subscribers only run in the dispatcher on drain."""
    _assert_scenario(suite_run, "T15")


def test_t16_topic_patterns_match_with_segment_precision(suite_run) -> None:
    """T16: topic patterns match with segment precision."""
    _assert_scenario(suite_run, "T16")


def test_t17_per_aggregate_order_survives_interleaved_concurrent_writers(suite_run) -> None:
    """T17: per-aggregate order survives interleaved concurrent writers."""
    _assert_scenario(suite_run, "T17")


def test_t18_acknowledged_deliveries_are_never_repeated(suite_run) -> None:
    """T18: acknowledged deliveries are never repeated."""
    _assert_scenario(suite_run, "T18")


def test_t19_a_delivery_that_fails_twice_still_succeeds_on_the_third_attempt(suite_run) -> None:
    """T19: a delivery that fails twice still succeeds on the third attempt."""
    _assert_scenario(suite_run, "T19")


def test_t20_a_delivery_is_dead_lettered_after_three_failed_attempts(suite_run) -> None:
    """T20: a delivery is dead-lettered after three failed attempts."""
    _assert_scenario(suite_run, "T20")


def test_t21_a_raising_handler_is_contained(suite_run) -> None:
    """T21: a raising handler is contained."""
    _assert_scenario(suite_run, "T21")


def test_t22_a_sync_delivery_that_fails_is_retried_like_an_async_one(suite_run) -> None:
    """T22: a sync delivery that fails is retried like an async one."""
    _assert_scenario(suite_run, "T22")


def test_t23_replay_re_delivers_matching_entries_in_order_in_the_caller_process(suite_run) -> None:
    """T23: replay re-delivers matching entries in order in the caller process."""
    _assert_scenario(suite_run, "T23")


def test_t24_subscription_bookkeeping(suite_run) -> None:
    """T24: subscription bookkeeping."""
    _assert_scenario(suite_run, "T24")


def test_t25_dedup_keys_are_unique_and_protected_by_an_identity(suite_run) -> None:
    """T25: dedup keys are unique and protected by an identity."""
    _assert_scenario(suite_run, "T25")


def test_t26_query_helpers_are_ordered_and_scoped(suite_run) -> None:
    """T26: query helpers are ordered and scoped."""
    _assert_scenario(suite_run, "T26")


def test_t27_reset_returns_the_subsystem_to_a_pristine_state(suite_run) -> None:
    """T27: reset returns the subsystem to a pristine state."""
    _assert_scenario(suite_run, "T27")
