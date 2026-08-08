defmodule OutboxTest do
  use ExUnit.Case, async: false

  alias Outbox.Ledger.Account
  alias Outbox.Eventing.Event
  alias Outbox.Eventing.Dispatcher
  alias Outbox.Eventing

  setup do
    # Reset dispatcher and sequence server to a pristine state before each test
    Dispatcher.reset()
    :ok
  end

  test "outbox capture: successful create/update/destroy writes are captured, reads are not" do
    # 1. Create (open)
    {:ok, account} =
      Account
      |> Ash.Changeset.for_create(:open, %{owner_id: "user_1", name: "Savings", balance: 100})
      |> Ash.create()

    events = Eventing.list_events!()
    assert length(events) == 1
    event = List.first(events)

    assert event.sequence == 1
    assert event.aggregate_sequence == 1
    assert event.topic == "ledger.account.open"
    assert event.resource == "Outbox.Ledger.Account"
    assert event.aggregate_type == "account"
    assert event.aggregate_id == to_string(account.id)
    assert event.action == :open
    assert event.actor_id == nil
    assert event.changes == %{"owner_id" => %{"from" => nil, "to" => "user_1"}, "name" => %{"from" => nil, "to" => "Savings"}, "balance" => %{"from" => nil, "to" => 100}, "status" => %{"from" => nil, "to" => "active"}}
    assert event.dedup_key == "account:#{account.id}:open:1"

    # 2. Update (rename)
    {:ok, updated_account} =
      account
      |> Ash.Changeset.for_update(:rename, %{name: "New Savings"})
      |> Ash.update()

    events = Eventing.list_events!()
    assert length(events) == 2
    event2 = List.last(events)

    assert event2.sequence == 2
    assert event2.aggregate_sequence == 2
    assert event2.topic == "ledger.account.rename"
    assert event2.aggregate_type == "account"
    assert event2.aggregate_id == to_string(account.id)
    assert event2.action == :rename
    assert event2.changes == %{"name" => %{"from" => "Savings", "to" => "New Savings"}}

    # 3. Read (should NOT produce any outbox entry)
    _read_accounts = Ash.read!(Account)
    assert length(Eventing.list_events!()) == 2

    # 4. Destroy (close)
    :ok =
      updated_account
      |> Ash.Changeset.for_destroy(:close)
      |> Ash.destroy!()

    events = Eventing.list_events!()
    assert length(events) == 3
    event3 = List.last(events)

    assert event3.sequence == 3
    assert event3.aggregate_sequence == 3
    assert event3.topic == "ledger.account.close"
    assert event3.action == :close
    assert event3.changes == %{}
  end

  test "outbox capture: failed write leaves no entry behind" do
    # Create account
    {:ok, account} =
      Account
      |> Ash.Changeset.for_create(:open, %{owner_id: "user_2", name: "Savings", balance: 50})
      |> Ash.create()

    assert length(Eventing.list_events!()) == 1

    # Attempt withdraw with insufficient funds (fails validation)
    res =
      account
      |> Ash.Changeset.for_update(:withdraw, %{amount: 100})
      |> Ash.update()

    assert {:error, _} = res

    # Outbox should still only have 1 entry
    assert length(Eventing.list_events!()) == 1
  end

  test "outbox capture: return_notifications?: true produces no outbox entry" do
    # Create account with return_notifications?: true
    {:ok, _account, notifications} =
      Account
      |> Ash.Changeset.for_create(:open, %{owner_id: "user_3", name: "Savings", balance: 100})
      |> Ash.create(return_notifications?: true)

    assert length(notifications) > 0

    # No outbox entry should be produced
    assert length(Eventing.list_events!()) == 0
  end

  test "outbox capture: batch writes produce exactly one entry per successfully written record" do
    # Create multiple accounts using BulkOps.open_many
    {:ok, accounts} = Outbox.Ledger.BulkOps.open_many([
      %{owner_id: "user_a", name: "Acc A", balance: 10},
      %{owner_id: "user_b", name: "Acc B", balance: 20}
    ])

    assert length(accounts) == 2
    events = Eventing.list_events!()
    assert length(events) == 2

    # Verify each event
    [event1, event2] = events
    assert event1.sequence == 1
    assert event1.topic == "ledger.account.open"
    assert event2.sequence == 2
    assert event2.topic == "ledger.account.open"

    # Freeze multiple accounts using BulkOps.freeze_many
    {:ok, frozen_accounts} = Outbox.Ledger.BulkOps.freeze_many(accounts)
    assert length(frozen_accounts) == 2

    # Outbox should now have 4 entries
    events = Eventing.list_events!()
    assert length(events) == 4

    [_, _, event3, event4] = events
    assert event3.sequence == 3
    assert event3.topic == "ledger.account.freeze"
    # Batch updates don't have pre-action records, so we check they only have "to" values correct
    assert event3.changes["status"] == %{"from" => nil, "to" => "frozen"}
    assert event4.sequence == 4
    assert event4.topic == "ledger.account.freeze"
    assert event4.changes["status"] == %{"from" => nil, "to" => "frozen"}
  end

  test "outbox entry contents: actor_id is recorded if actor has binary id" do
    actor = %{id: "actor_123"}
    {:ok, _account} =
      Account
      |> Ash.Changeset.for_create(:open, %{owner_id: "user_actor", name: "Savings"})
      |> Ash.create(actor: actor)

    events = Eventing.list_events!()
    assert length(events) == 1
    assert List.first(events).actor_id == "actor_123"
  end

  test "outbox entry contents: actor_id is nil if actor has non-binary id or no id" do
    actor = %{id: 123} # non-binary
    {:ok, _account} =
      Account
      |> Ash.Changeset.for_create(:open, %{owner_id: "user_actor2", name: "Savings"})
      |> Ash.create(actor: actor)

    events = Eventing.list_events!()
    assert length(events) == 1
    assert List.first(events).actor_id == nil
  end

  test "dispatcher: subscribe, unsubscribe, and pattern matching" do
    parent = self()

    # 1. Subscribe with literal pattern
    assert :ok = Dispatcher.subscribe(:sub_1, "ledger.account.open", fn event ->
      send(parent, {:sub_1, event})
      :ok
    end, mode: :sync)

    # Subscribe with * wildcard
    assert :ok = Dispatcher.subscribe(:sub_2, "ledger.*.open", fn event ->
      send(parent, {:sub_2, event})
      :ok
    end, mode: :sync)

    # Subscribe with # wildcard (matches all ledger events)
    assert :ok = Dispatcher.subscribe(:sub_3, "ledger.#", fn event ->
      send(parent, {:sub_3, event})
      :ok
    end, mode: :sync)

    # Subscribe with non-matching pattern
    assert :ok = Dispatcher.subscribe(:sub_4, "ledger.transfer.*", fn event ->
      send(parent, {:sub_4, event})
      :ok
    end, mode: :sync)

    # Try subscribing with same ID (should fail)
    assert {:error, :already_subscribed} = Dispatcher.subscribe(:sub_1, "ledger.account.rename", fn _ -> :ok end)

    # Trigger a write (open account)
    {:ok, account} =
      Account
      |> Ash.Changeset.for_create(:open, %{owner_id: "u1", name: "Savings"})
      |> Ash.create()

    # Since they are :sync, they should be processed immediately in the write process
    assert_receive {:sub_1, %Event{topic: "ledger.account.open"}}
    assert_receive {:sub_2, %Event{topic: "ledger.account.open"}}
    assert_receive {:sub_3, %Event{topic: "ledger.account.open"}}
    refute_receive {:sub_4, _}

    # 2. Unsubscribe
    assert :ok = Dispatcher.unsubscribe(:sub_1)

    # Trigger another write
    {:ok, _updated} =
      account
      |> Ash.Changeset.for_update(:rename, %{name: "Renamed"})
      |> Ash.update()

    # sub_1 should not receive anything because it unsubscribed
    refute_receive {:sub_1, _}
    # sub_3 should receive ledger.account.rename because of "ledger.#"
    assert_receive {:sub_3, %Event{topic: "ledger.account.rename"}}
  end

  test "dispatcher: subscriber only receives entries created after subscription" do
    parent = self()

    # Create an event BEFORE subscription
    {:ok, account} =
      Account
      |> Ash.Changeset.for_create(:open, %{owner_id: "u2", name: "Savings"})
      |> Ash.create()

    # Subscribe now
    assert :ok = Dispatcher.subscribe(:sub_after, "ledger.account.#", fn event ->
      send(parent, {:sub_after, event})
      :ok
    end, mode: :sync)

    # Trigger another write
    {:ok, _updated} =
      account
      |> Ash.Changeset.for_update(:rename, %{name: "Renamed"})
      |> Ash.update()

    # Should only receive the rename event (sequence 2), not the open event (sequence 1)
    assert_receive {:sub_after, %Event{sequence: 2, topic: "ledger.account.rename"}}
    refute_receive {:sub_after, %Event{sequence: 1}}
  end

  test "dispatcher: sync vs async delivery modes" do
    parent = self()

    # Subscribe :sync
    assert :ok = Dispatcher.subscribe(:sub_sync, "ledger.account.open", fn event ->
      send(parent, {:sync_called, self(), event})
      :ok
    end, mode: :sync)

    # Subscribe :async
    assert :ok = Dispatcher.subscribe(:sub_async, "ledger.account.open", fn event ->
      send(parent, {:async_called, self(), event})
      :ok
    end, mode: :async)

    # Trigger write
    {:ok, _account} =
      Account
      |> Ash.Changeset.for_create(:open, %{owner_id: "u3", name: "Savings"})
      |> Ash.create()

    # :sync handler should have run immediately in the writer process (self())
    assert_receive {:sync_called, writer_pid, %Event{sequence: 1}}
    assert writer_pid == self()

    # :async handler should NOT have run yet
    refute_receive {:async_called, _, _}

    # Now request a drain (flush)
    assert :ok = Dispatcher.flush()

    # :async handler should run in the dispatcher process (not writer_pid)
    assert_receive {:async_called, dispatcher_pid, %Event{sequence: 1}}
    assert dispatcher_pid != self()
  end

  test "dispatcher: sync handler failure is retried on flush" do
    parent = self()

    # Subscribe :sync but handler fails on first call
    # We use an agent to track the call count
    {:ok, count_agent} = Agent.start_link(fn -> 0 end)

    assert :ok = Dispatcher.subscribe(:sub_sync_fail, "ledger.account.open", fn event ->
      count = Agent.get_and_update(count_agent, fn c -> {c, c + 1} end)
      send(parent, {:sync_call, count, event})
      if count == 0 do
        {:error, :temporary_failure}
      else
        :ok
      end
    end, mode: :sync)

    # Trigger write
    {:ok, _account} =
      Account
      |> Ash.Changeset.for_create(:open, %{owner_id: "u4", name: "Savings"})
      |> Ash.create()

    # First call (sync) happens immediately and fails
    assert_receive {:sync_call, 0, %Event{sequence: 1}}

    # Now requested drain (flush) should retry it
    assert :ok = Dispatcher.flush()

    # Second call happens during flush and succeeds
    assert_receive {:sync_call, 1, %Event{sequence: 1}}

    # Another flush should NOT retry it (already acknowledged)
    assert :ok = Dispatcher.flush()
    refute_receive {:sync_call, _, _}
  end

  test "dispatcher: bounded retries and dead-letter path" do
    parent = self()

    # Subscribe :async, handler always fails with an error
    assert :ok = Dispatcher.subscribe(:sub_always_fail, "ledger.account.open", fn event ->
      send(parent, {:attempt, event.sequence})
      {:error, :hard_error}
    end, mode: :async)

    # Subscribe :async, handler always raises an exception
    assert :ok = Dispatcher.subscribe(:sub_always_raise, "ledger.account.open", fn event ->
      send(parent, {:attempt_raise, event.sequence})
      raise "boom"
    end, mode: :async)

    # Trigger write
    {:ok, _account} =
      Account
      |> Ash.Changeset.for_create(:open, %{owner_id: "u5", name: "Savings"})
      |> Ash.create()

    # Pass 1: Attempt 1
    assert :ok = Dispatcher.flush()
    assert_receive {:attempt, 1}
    assert_receive {:attempt_raise, 1}

    # Pass 2: Attempt 2
    assert :ok = Dispatcher.flush()
    assert_receive {:attempt, 1}
    assert_receive {:attempt_raise, 1}

    # Pass 3: Attempt 3
    assert :ok = Dispatcher.flush()
    assert_receive {:attempt, 1}
    assert_receive {:attempt_raise, 1}

    # Pass 4: Should NOT attempt anymore because they are dead-lettered
    assert :ok = Dispatcher.flush()
    refute_receive {:attempt, 1}
    refute_receive {:attempt_raise, 1}

    # Check dead letters
    dls = Dispatcher.dead_letters()
    assert length(dls) == 2

    # Sorted by sequence ascending and subscriber registration order
    [dl1, dl2] = dls
    assert dl1.subscriber_id == :sub_always_fail
    assert dl1.sequence == 1
    assert dl1.attempts == 3
    assert dl1.reason == :hard_error

    assert dl2.subscriber_id == :sub_always_raise
    assert dl2.sequence == 1
    assert dl2.attempts == 3
    assert dl2.reason == {:raised, "boom"}
  end

  test "replay: replay capability via generic action" do
    parent = self()

    # Trigger some writes
    {:ok, account} =
      Account
      |> Ash.Changeset.for_create(:open, %{owner_id: "u6", name: "Savings"})
      |> Ash.create()

    {:ok, _} =
      account
      |> Ash.Changeset.for_update(:rename, %{name: "New Savings"})
      |> Ash.update()

    # Subscribe now so we only receive future events under normal dispatcher rules
    assert :ok = Dispatcher.subscribe(:sub_replay, "ledger.account.#", fn event ->
      send(parent, {:normal, event.sequence})
      :ok
    end, mode: :async)

    # Replay after sequence 0
    {:ok, delivered} = Eventing.replay(0, :sub_replay)
    assert delivered == [1, 2]

    # Replay after sequence 1
    {:ok, delivered2} = Eventing.replay(1, :sub_replay)
    assert delivered2 == [2]

    # Replay for unknown subscriber should yield {:ok, []}
    {:ok, delivered3} = Eventing.replay(0, :unknown_sub)
    assert delivered3 == []
  end

  test "concurrency: global and per-aggregate sequences are correct under concurrent writes" do
    # Concurrently write to the same account and different accounts
    {:ok, account_1} =
      Account
      |> Ash.Changeset.for_create(:open, %{owner_id: "c1", name: "Acc 1"})
      |> Ash.create()

    {:ok, account_2} =
      Account
      |> Ash.Changeset.for_create(:open, %{owner_id: "c2", name: "Acc 2"})
      |> Ash.create()

    # We will spawn 10 processes to perform deposits concurrently
    tasks =
      for i <- 1..10 do
        Task.async(fn ->
          # Even processes write to account_1, odd to account_2
          if rem(i, 2) == 0 do
            account_1
            |> Ash.Changeset.for_update(:deposit, %{amount: 10})
            |> Ash.update!()
          else
            account_2
            |> Ash.Changeset.for_update(:deposit, %{amount: 10})
            |> Ash.update!()
          end
        end)
      end

    # Wait for all tasks to complete
    Enum.each(tasks, &Task.await/1)

    # We had 2 opens, plus 10 deposits = 12 events total
    events = Eventing.list_events!()
    assert length(events) == 12

    # Global sequences must be 1..12 exactly
    sequences = Enum.map(events, & &1.sequence)
    assert sequences == Enum.to_list(1..12)

    # Check per-aggregate sequences for account_1 and account_2
    events_1 = Eventing.events_for!("account", to_string(account_1.id))
    # 1 open + 5 deposits = 6 events
    assert length(events_1) == 6
    assert Enum.map(events_1, & &1.aggregate_sequence) == Enum.to_list(1..6)

    events_2 = Eventing.events_for!("account", to_string(account_2.id))
    # 1 open + 5 deposits = 6 events
    assert length(events_2) == 6
    assert Enum.map(events_2, & &1.aggregate_sequence) == Enum.to_list(1..6)
  end
end
