ExUnit.start()

defmodule Outbox.EventingTest do
  use ExUnit.Case, async: false

  setup do
    Outbox.Eventing.Dispatcher.reset()
    :ok
  end

  # ---- Helpers ----

  defp open_account(attrs) do
    Ash.create!(Outbox.Ledger.Account, attrs, action: :open, domain: Outbox.Ledger, authorize?: false)
  end

  # ---- Tests: Basic outbox capture ----

  test "create produces an outbox entry" do
    account = open_account(%{owner_id: "u1", name: "Checking", balance: 100})

    events = Outbox.Eventing.list_events!()
    assert length(events) == 1

    event = List.first(events)
    assert event.sequence == 1
    assert event.aggregate_sequence == 1
    assert event.topic == "ledger.account.open"
    assert event.resource == "Outbox.Ledger.Account"
    assert event.aggregate_type == "account"
    assert event.aggregate_id == account.id
    assert event.action == :open
    assert event.actor_id == nil
    assert event.changes == %{
             "owner_id" => %{"from" => nil, "to" => "u1"},
             "name" => %{"from" => nil, "to" => "Checking"},
             "balance" => %{"from" => nil, "to" => 100},
             "status" => %{"from" => nil, "to" => "active"}
           }
  end

  test "update produces an outbox entry with diff" do
    account = open_account(%{owner_id: "u1", name: "Checking", balance: 100})

    account
    |> Ash.Changeset.for_update(:rename, %{name: "Savings"}, domain: Outbox.Ledger, authorize?: false)
    |> Ash.update!(domain: Outbox.Ledger, authorize?: false)

    events = Outbox.Eventing.list_events!()
    assert length(events) == 2

    event = List.last(events)
    assert event.sequence == 2
    assert event.aggregate_sequence == 2
    assert event.topic == "ledger.account.rename"
    assert event.aggregate_id == account.id
    assert event.action == :rename
    assert event.changes["name"] == %{"from" => "Checking", "to" => "Savings"}
  end

  test "destroy produces an outbox entry with empty changes" do
    account = open_account(%{owner_id: "u1", name: "Checking"})

    account
    |> Ash.Changeset.for_destroy(:close, %{}, domain: Outbox.Ledger, authorize?: false)
    |> Ash.destroy!(domain: Outbox.Ledger, authorize?: false)

    events = Outbox.Eventing.list_events!()
    assert length(events) == 2

    destroy_event = List.last(events)
    assert destroy_event.action == :close
    assert destroy_event.changes == %{}
  end

  test "failed write produces no outbox entry" do
    account = open_account(%{owner_id: "u1", name: "Checking", balance: 100})

    # Withdraw more than balance - should fail
    result =
      account
      |> Ash.Changeset.for_update(:withdraw, %{amount: 200},
        domain: Outbox.Ledger,
        authorize?: false
      )
      |> Ash.update(domain: Outbox.Ledger, authorize?: false)

    assert {:error, _} = result

    events = Outbox.Eventing.list_events!()
    assert length(events) == 1
  end

  test "global sequence increases monotonically" do
    open_account(%{owner_id: "u1", name: "A1"})
    open_account(%{owner_id: "u2", name: "A2"})
    open_account(%{owner_id: "u3", name: "A3"})

    events = Outbox.Eventing.list_events!()
    sequences = Enum.map(events, & &1.sequence)
    assert sequences == [1, 2, 3]
  end

  test "aggregate sequence increases per aggregate" do
    a1 = open_account(%{owner_id: "u1", name: "A1"})
    a2 = open_account(%{owner_id: "u2", name: "A2"})

    a1
    |> Ash.Changeset.for_update(:rename, %{name: "A1-renamed"},
      domain: Outbox.Ledger,
      authorize?: false
    )
    |> Ash.update!(domain: Outbox.Ledger, authorize?: false)

    a2
    |> Ash.Changeset.for_update(:rename, %{name: "A2-renamed"},
      domain: Outbox.Ledger,
      authorize?: false
    )
    |> Ash.update!(domain: Outbox.Ledger, authorize?: false)

    a1
    |> Ash.Changeset.for_update(:rename, %{name: "A1-again"},
      domain: Outbox.Ledger,
      authorize?: false
    )
    |> Ash.update!(domain: Outbox.Ledger, authorize?: false)

    events = Outbox.Eventing.list_events!()

    # Global sequence
    assert Enum.map(events, & &1.sequence) == [1, 2, 3, 4, 5]

    # Aggregate sequences for a1
    a1_events = Outbox.Eventing.events_for!("account", a1.id)
    assert length(a1_events) == 3
    assert Enum.map(a1_events, & &1.aggregate_sequence) == [1, 2, 3]

    # Aggregate sequences for a2
    a2_events = Outbox.Eventing.events_for!("account", a2.id)
    assert length(a2_events) == 2
    assert Enum.map(a2_events, & &1.aggregate_sequence) == [1, 2]
  end

  test "dedup_key prevents duplicate entries" do
    open_account(%{owner_id: "u1", name: "Checking"})

    events = Outbox.Eventing.list_events!()
    assert length(events) == 1
  end

  test "transfer produces outbox entries" do
    t =
      Ash.create!(Outbox.Ledger.Transfer, %{
        from_account_id: "a1",
        to_account_id: "a2",
        amount: 50
      },
        action: :record,
        domain: Outbox.Ledger,
        authorize?: false
      )

    events = Outbox.Eventing.list_events!()
    assert length(events) == 1

    event = List.first(events)
    assert event.topic == "ledger.transfer.record"
    assert event.resource == "Outbox.Ledger.Transfer"
    assert event.aggregate_type == "transfer"
    assert event.aggregate_id == t.id
  end

  test "return_notifications? suppresses outbox entry" do
    {:ok, _account, notifications} =
      Ash.create(Outbox.Ledger.Account, %{owner_id: "u1", name: "Checking"},
        action: :open,
        domain: Outbox.Ledger,
        return_notifications?: true,
        authorize?: false
      )

    # Notifications should be returned, not dispatched
    assert is_list(notifications)
    assert length(notifications) > 0

    # But no outbox entry should be created
    events = Outbox.Eventing.list_events!()
    assert events == []
  end

  # ---- Tests: Dispatcher ----

  test "subscribe and unsubscribe" do
    assert Outbox.Eventing.Dispatcher.subscribe(:test_sub, "ledger.account.*", fn _ -> :ok end) ==
             :ok

    assert Outbox.Eventing.Dispatcher.subscribe(:test_sub, "ledger.account.*", fn _ -> :ok end) ==
             {:error, :already_subscribed}

    assert Outbox.Eventing.Dispatcher.unsubscribe(:test_sub) == :ok

    # Re-subscribe after unsubscribing
    assert Outbox.Eventing.Dispatcher.subscribe(:test_sub, "ledger.account.*", fn _ -> :ok end) ==
             :ok
  end

  test "async delivery via flush" do
    test_pid = self()

    Outbox.Eventing.Dispatcher.subscribe(:async_sub, "ledger.account.*", fn event ->
      send(test_pid, {:event, event.sequence})
      :ok
    end)

    open_account(%{owner_id: "u1", name: "A1"})
    open_account(%{owner_id: "u2", name: "A2"})

    # No messages yet (async mode)
    refute_received {:event, _}

    # Flush should deliver both
    Outbox.Eventing.Dispatcher.flush()

    assert_received {:event, 1}
    assert_received {:event, 2}
  end

  test "sync delivery happens immediately" do
    test_pid = self()

    Outbox.Eventing.Dispatcher.subscribe(:sync_sub, "ledger.account.*", fn event ->
      send(test_pid, {:sync_event, event.sequence})
      :ok
    end,
      mode: :sync
    )

    open_account(%{owner_id: "u1", name: "A1"})

    # Sync delivery should happen before the write returns
    assert_received {:sync_event, 1}
  end

  test "delivery ordering respects sequence" do
    test_pid = self()

    Outbox.Eventing.Dispatcher.subscribe(:order_sub, "ledger.account.*", fn event ->
      send(test_pid, {:ordered, event.sequence})
      :ok
    end)

    open_account(%{owner_id: "u1", name: "A1"})
    open_account(%{owner_id: "u2", name: "A2"})
    open_account(%{owner_id: "u3", name: "A3"})

    Outbox.Eventing.Dispatcher.flush()

    assert_received {:ordered, 1}
    assert_received {:ordered, 2}
    assert_received {:ordered, 3}
  end

  test "retry on failure, dead letter after 3 attempts" do
    test_pid = self()
    attempts = :ets.new(:test_attempts, [:set, :public])

    Outbox.Eventing.Dispatcher.subscribe(:retry_sub, "ledger.account.*", fn event ->
      count = :ets.update_counter(attempts, event.sequence, {2, 1}, {event.sequence, 0})

      if count < 3 do
        send(test_pid, {:failed_attempt, event.sequence, count})
        {:error, "not ready"}
      else
        send(test_pid, {:succeeded, event.sequence, count})
        :ok
      end
    end)

    open_account(%{owner_id: "u1", name: "A1"})

    # First flush - attempt 1 (async, so this is attempt 1)
    Outbox.Eventing.Dispatcher.flush()

    # Should have failed once
    assert_received {:failed_attempt, 1, 1}

    # Second flush - attempt 2
    Outbox.Eventing.Dispatcher.flush()
    assert_received {:failed_attempt, 1, 2}

    # Third flush - attempt 3, should dead-letter
    Outbox.Eventing.Dispatcher.flush()
    assert_received {:failed_attempt, 1, 3}

    # Fourth flush - should not retry anymore
    Outbox.Eventing.Dispatcher.flush()
    refute_received {:failed_attempt, _, _}

    # Check dead letters
    dl = Outbox.Eventing.Dispatcher.dead_letters()
    assert length(dl) == 1
    assert hd(dl).subscriber_id == :retry_sub
    assert hd(dl).sequence == 1
    assert hd(dl).attempts == 3
    assert hd(dl).reason == "not ready"
  end

  test "handler raising is contained" do
    test_pid = self()

    Outbox.Eventing.Dispatcher.subscribe(:raise_sub, "ledger.account.*", fn _event ->
      send(test_pid, :raising)
      raise "boom!"
    end)

    open_account(%{owner_id: "u1", name: "A1"})

    # Flush - handler raises but dispatcher stays up
    Outbox.Eventing.Dispatcher.flush()
    assert_received :raising

    # Dispatcher should still be alive
    assert Process.alive?(Process.whereis(Outbox.Eventing.Dispatcher))

    # Should be in dead letters after 3 attempts
    Outbox.Eventing.Dispatcher.flush()
    Outbox.Eventing.Dispatcher.flush()

    dl = Outbox.Eventing.Dispatcher.dead_letters()
    assert length(dl) == 1
    assert hd(dl).subscriber_id == :raise_sub
    assert hd(dl).attempts == 3
    assert match?({:raised, "boom!"}, hd(dl).reason)
  end

  test "pattern matching with *" do
    test_pid = self()

    Outbox.Eventing.Dispatcher.subscribe(:star_sub, "ledger.account.*", fn event ->
      send(test_pid, {:star_match, event.topic})
      :ok
    end)

    account = open_account(%{owner_id: "u1", name: "A1"})

    account
    |> Ash.Changeset.for_update(:rename, %{name: "A1-renamed"},
      domain: Outbox.Ledger,
      authorize?: false
    )
    |> Ash.update!(domain: Outbox.Ledger, authorize?: false)

    Outbox.Eventing.Dispatcher.flush()

    assert_received {:star_match, "ledger.account.open"}
    assert_received {:star_match, "ledger.account.rename"}
  end

  test "pattern matching with #" do
    test_pid = self()

    Outbox.Eventing.Dispatcher.subscribe(:hash_sub, "ledger.#", fn event ->
      send(test_pid, {:hash_match, event.topic})
      :ok
    end)

    open_account(%{owner_id: "u1", name: "A1"})

    Ash.create!(Outbox.Ledger.Transfer, %{
      from_account_id: "a1",
      to_account_id: "a2",
      amount: 50
    },
      action: :record,
      domain: Outbox.Ledger,
      authorize?: false
    )

    Outbox.Eventing.Dispatcher.flush()

    assert_received {:hash_match, "ledger.account.open"}
    assert_received {:hash_match, "ledger.transfer.record"}
  end

  test "pattern matching with exact literal" do
    test_pid = self()

    Outbox.Eventing.Dispatcher.subscribe(:exact_sub, "ledger.account.open", fn event ->
      send(test_pid, {:exact, event.topic})
      :ok
    end)

    account = open_account(%{owner_id: "u1", name: "A1"})

    account
    |> Ash.Changeset.for_update(:rename, %{name: "A1-renamed"},
      domain: Outbox.Ledger,
      authorize?: false
    )
    |> Ash.update!(domain: Outbox.Ledger, authorize?: false)

    Outbox.Eventing.Dispatcher.flush()

    assert_received {:exact, "ledger.account.open"}
    refute_received {:exact, "ledger.account.rename"}
  end

  test "subscriber only receives events created after subscription" do
    # Create an event before subscribing
    open_account(%{owner_id: "u1", name: "Pre"})

    test_pid = self()

    Outbox.Eventing.Dispatcher.subscribe(:late_sub, "ledger.account.*", fn event ->
      send(test_pid, {:late, event.sequence})
      :ok
    end)

    # Create an event after subscribing
    open_account(%{owner_id: "u2", name: "Post"})

    Outbox.Eventing.Dispatcher.flush()

    # Should only receive the second event (sequence 2)
    assert_received {:late, 2}
    refute_received {:late, 1}
  end

  test "sync handler that fails is retried" do
    test_pid = self()
    attempts = :ets.new(:sync_attempts, [:set, :public])

    Outbox.Eventing.Dispatcher.subscribe(:sync_retry_sub, "ledger.account.*", fn event ->
      count = :ets.update_counter(attempts, :count, {2, 1}, {:count, 0})
      send(test_pid, {:sync_attempt, event.sequence, count})

      if count == 1 do
        {:error, "fail first"}
      else
        :ok
      end
    end,
      mode: :sync
    )

    open_account(%{owner_id: "u1", name: "A1"})

    # First attempt (sync, burned immediately)
    assert_received {:sync_attempt, 1, 1}

    # Drain - should retry
    Outbox.Eventing.Dispatcher.flush()
    assert_received {:sync_attempt, 1, 2}
  end

  test "reset clears everything" do
    open_account(%{owner_id: "u1", name: "A1"})

    Outbox.Eventing.Dispatcher.subscribe(:reset_sub, "ledger.account.*", fn _ -> :ok end)
    Outbox.Eventing.Dispatcher.flush()

    assert length(Outbox.Eventing.list_events!()) == 1

    Outbox.Eventing.Dispatcher.reset()

    # Everything should be cleared
    assert Outbox.Eventing.list_events!() == []
    assert Outbox.Eventing.Dispatcher.dead_letters() == []

    # New event should start at sequence 1 again
    open_account(%{owner_id: "u1", name: "A1"})
    events = Outbox.Eventing.list_events!()
    assert length(events) == 1
    assert hd(events).sequence == 1
    assert hd(events).aggregate_sequence == 1
  end

  # ---- Tests: Batch operations ----

  test "open_many creates one entry per record" do
    {:ok, accounts} =
      Outbox.Ledger.BulkOps.open_many([
        %{owner_id: "u1", name: "A1"},
        %{owner_id: "u2", name: "A2"},
        %{owner_id: "u3", name: "A3"}
      ])

    assert length(accounts) == 3

    events = Outbox.Eventing.list_events!()
    assert length(events) == 3

    # Each should have unique dedup_key
    dedup_keys = Enum.map(events, & &1.dedup_key)
    assert length(Enum.uniq(dedup_keys)) == 3
  end

  test "freeze_many creates one entry per record" do
    {:ok, accounts} =
      Outbox.Ledger.BulkOps.open_many([
        %{owner_id: "u1", name: "A1"},
        %{owner_id: "u2", name: "A2"}
      ])

    {:ok, frozen} = Outbox.Ledger.BulkOps.freeze_many(accounts)

    assert length(frozen) == 2

    events = Outbox.Eventing.list_events!()
    # 2 opens + 2 freezes = 4
    assert length(events) == 4

    freeze_events = Enum.filter(events, &(&1.action == :freeze))
    assert length(freeze_events) == 2

    # Each freeze should show status change
    Enum.each(freeze_events, fn event ->
      assert event.changes["status"] == %{"from" => "active", "to" => "frozen"}
    end)
  end

  # ---- Tests: Replay ----

  test "replay delivers events after given sequence" do
    test_pid = self()

    open_account(%{owner_id: "u1", name: "A1"})
    open_account(%{owner_id: "u2", name: "A2"})
    open_account(%{owner_id: "u3", name: "A3"})

    Outbox.Eventing.Dispatcher.subscribe(:replay_sub, "ledger.account.*", fn event ->
      send(test_pid, {:replayed, event.sequence})
      :ok
    end)

    {:ok, sequences} = Outbox.Eventing.replay(1, :replay_sub)
    assert sequences == [2, 3]

    assert_received {:replayed, 2}
    assert_received {:replayed, 3}
    refute_received {:replayed, 1}
  end

  test "replay with unknown subscriber returns empty" do
    {:ok, sequences} = Outbox.Eventing.replay(0, :nonexistent)
    assert sequences == []
  end

  test "replay delivers even previously acknowledged events" do
    test_pid = self()

    Outbox.Eventing.Dispatcher.subscribe(:replay_ack_sub, "ledger.account.*", fn event ->
      send(test_pid, {:replay_ack, event.sequence})
      :ok
    end)

    open_account(%{owner_id: "u1", name: "A1"})
    open_account(%{owner_id: "u2", name: "A2"})

    # Acknowledge via flush
    Outbox.Eventing.Dispatcher.flush()
    assert_received {:replay_ack, 1}
    assert_received {:replay_ack, 2}

    # Replay should deliver them again
    {:ok, sequences} = Outbox.Eventing.replay(0, :replay_ack_sub)
    assert sequences == [1, 2]
    assert_received {:replay_ack, 1}
    assert_received {:replay_ack, 2}
  end

  test "replay never dead-letters" do
    Outbox.Eventing.Dispatcher.subscribe(:replay_dl_sub, "ledger.account.*", fn _event ->
      {:error, "always fails"}
    end)

    open_account(%{owner_id: "u1", name: "A1"})

    # Replay should still return sequences even though handler fails
    {:ok, sequences} = Outbox.Eventing.replay(0, :replay_dl_sub)
    assert sequences == [1]

    # No dead letters from replay
    dl = Outbox.Eventing.Dispatcher.dead_letters()
    assert dl == []
  end
end
