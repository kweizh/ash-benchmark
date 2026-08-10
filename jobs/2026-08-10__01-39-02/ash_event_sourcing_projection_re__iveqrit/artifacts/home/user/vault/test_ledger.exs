# Run this script with: mix run test_ledger.exs

# Start the application first to ensure everything is initialized
Application.ensure_all_started(:vault)

defmodule TestLedger do
  alias Vault.Ledger
  alias Vault.Ledger.Event
  alias Vault.Ledger.Snapshot
  alias Vault.Ledger.AccountProjection
  alias Vault.Ledger.Checkpoint
  alias Vault.Ledger.Fold
  alias Vault.Ledger.Aggregate
  alias Vault.Ledger.Projector
  alias Vault.Ledger.Snapshots

  def run_tests do
    IO.puts("=== Running Comprehensive Event-Sourced Ledger Tests ===")

    test_payload_and_types()
    test_fold()
    test_append_and_store_contracts()
    test_commands_and_invariants()
    test_snapshots()
    test_aggregate_reconstruction()
    test_projector_and_rebuild()

    IO.puts("\n🎉 ALL TESTS PASSED SUCCESSFULLY!")
  end

  defp assert!(value, msg) do
    if not value do
      raise "Assertion Failed: #{msg}"
    end
  end

  defp assert_error!(fun, expected_error_class, field, message) do
    try do
      fun.()
      raise "Expected error but function succeeded"
    rescue
      e ->
        if is_struct(e, Ash.Error.Invalid) do
          inner = List.first(e.errors)
          assert!(inner != nil, "Expected wrapped error inside Ash.Error.Invalid")
          cond do
            expected_error_class == Ash.Error.Invalid.NoSuchInput ->
              assert!(is_struct(inner, Ash.Error.Invalid.NoSuchInput), "Expected inner to be NoSuchInput")

            expected_error_class == Ash.Error.Changes.InvalidAttribute ->
              assert!(is_struct(inner, Ash.Error.Changes.InvalidAttribute), "Expected inner to be InvalidAttribute")
              assert!(inner.field == field, "Expected field #{inspect(field)}, got #{inspect(inner.field)}")
              assert!(inner.message == message, "Expected message #{inspect(message)}, got #{inspect(inner.message)}")

            expected_error_class == Ash.Error.Changes.InvalidChanges ->
              assert!(is_struct(inner, Ash.Error.Changes.InvalidChanges), "Expected inner to be InvalidChanges")
              assert!(inner.fields == field, "Expected fields #{inspect(field)}, got #{inspect(inner.fields)}")
              assert!(inner.message == message, "Expected message #{inspect(message)}, got #{inspect(inner.message)}")

            expected_error_class == Ash.Error.Action.InvalidArgument ->
              assert!(is_struct(inner, Ash.Error.Action.InvalidArgument), "Expected inner to be InvalidArgument")
              assert!(inner.field == field, "Expected field #{inspect(field)}, got #{inspect(inner.field)}")
              assert!(inner.message == message, "Expected message #{inspect(message)}, got #{inspect(inner.message)}")

            true ->
              IO.inspect(inner, label: "ACTUAL INNER ERROR")
              assert!(is_struct(inner, expected_error_class), "Expected inner to be #{inspect(expected_error_class)}")
          end
        else
          IO.inspect(e, label: "ACTUAL DIRECT ERROR")
          assert!(is_struct(e, expected_error_class), "Expected directly raised #{inspect(expected_error_class)}")
          cond do
            expected_error_class == Ash.Error.Changes.InvalidAttribute ->
              assert!(e.field == field, "Expected field #{inspect(field)}, got #{inspect(e.field)}")
              assert!(e.message == message, "Expected message #{inspect(message)}, got #{inspect(e.message)}")

            expected_error_class == Ash.Error.Changes.InvalidChanges ->
              assert!(e.fields == field, "Expected fields #{inspect(field)}, got #{inspect(e.fields)}")
              assert!(e.message == message, "Expected message #{inspect(message)}, got #{inspect(e.message)}")

            true ->
              :ok
          end
        end
    end
  end

  def test_payload_and_types do
    IO.puts("\n--- Testing Typed Payloads ---")

    # Test casting valid maps into Vault.Ledger.Payload
    # Account Opened
    opened_payload = %{"type" => "account_opened", "owner" => "Alice", "opening_balance_cents" => 1000}
    {:ok, casted_opened} = Ash.Type.cast_input(Vault.Ledger.Payload, opened_payload)
    assert!(casted_opened.type == :account_opened, "type should be :account_opened")
    assert!(casted_opened.value.owner == "Alice", "owner should be Alice")
    assert!(casted_opened.value.opening_balance_cents == 1000, "balance should be 1000")

    # Deposited
    deposited_payload = %{"type" => "deposited", "amount_cents" => 500}
    {:ok, casted_deposited} = Ash.Type.cast_input(Vault.Ledger.Payload, deposited_payload)
    assert!(casted_deposited.type == :deposited, "type should be :deposited")
    assert!(casted_deposited.value.amount_cents == 500, "amount should be 500")

    # Withdrawn
    withdrawn_payload = %{"type" => "withdrawn", "amount_cents" => 200}
    {:ok, casted_withdrawn} = Ash.Type.cast_input(Vault.Ledger.Payload, withdrawn_payload)
    assert!(casted_withdrawn.type == :withdrawn, "type should be :withdrawn")
    assert!(casted_withdrawn.value.amount_cents == 200, "amount should be 200")

    # Frozen
    frozen_payload = %{"type" => "frozen", "reason" => "fraud_review"}
    {:ok, casted_frozen} = Ash.Type.cast_input(Vault.Ledger.Payload, frozen_payload)
    assert!(casted_frozen.type == :frozen, "type should be :frozen")
    assert!(casted_frozen.value.reason == :fraud_review, "reason should be :fraud_review")

    # Unfrozen
    unfrozen_payload = %{"type" => "unfrozen", "note" => "all clear"}
    {:ok, casted_unfrozen} = Ash.Type.cast_input(Vault.Ledger.Payload, unfrozen_payload)
    assert!(casted_unfrozen.type == :unfrozen, "type should be :unfrozen")
    assert!(casted_unfrozen.value.note == "all clear", "note should be 'all clear'")

    # Test invalid values and types
    assert!(match?({:error, _}, Ash.Type.cast_input(Vault.Ledger.Payload, %{"type" => "unknown"})), "unknown type should fail")
    assert!(match?({:error, _}, Ash.Type.cast_input(Vault.Ledger.Payload, %{"type" => "account_opened", "owner" => "", "opening_balance_cents" => 100})), "empty owner should fail")
    assert!(match?({:error, _}, Ash.Type.cast_input(Vault.Ledger.Payload, %{"type" => "account_opened", "owner" => "A", "opening_balance_cents" => -1})), "negative opening balance should fail")
    assert!(match?({:error, _}, Ash.Type.cast_input(Vault.Ledger.Payload, %{"type" => "deposited", "amount_cents" => 0})), "deposited amount must be >= 1")
    assert!(match?({:error, _}, Ash.Type.cast_input(Vault.Ledger.Payload, %{"type" => "frozen", "reason" => "invalid"})), "invalid frozen reason should fail")
    assert!(match?({:error, _}, Ash.Type.cast_input(Vault.Ledger.Payload, %{"type" => "unfrozen", "note" => String.duplicate("a", 121)})), "note too long should fail")

    IO.puts("Typed payloads validated successfully.")
  end

  def test_fold do
    IO.puts("\n--- Testing Pure Fold logic ---")

    # 1. Initial State
    state = Fold.initial("acc_1")
    assert!(state.account_id == "acc_1", "initial account_id")
    assert!(state.owner == nil, "initial owner is nil")
    assert!(state.balance_cents == 0, "initial balance is 0")
    assert!(state.status == :absent, "initial status is :absent")
    assert!(state.version == 0, "initial version is 0")

    # 2. Event Apply - Account Opened
    e1 = %Event{
      account_id: "acc_1",
      version: 1,
      sequence: 1,
      payload: %Ash.Union{type: :account_opened, value: %Vault.Ledger.Payloads.AccountOpened{owner: "Bob", opening_balance_cents: 1000}},
      recorded_at: DateTime.utc_now()
    }
    {:ok, state} = Fold.apply_event(state, e1)
    assert!(state.owner == "Bob", "ownerBob")
    assert!(state.balance_cents == 1000, "balance 1000")
    assert!(state.status == :open, "status open")
    assert!(state.version == 1, "version 1")

    # 3. Event Apply - Deposited
    e2 = %Event{
      account_id: "acc_1",
      version: 2,
      sequence: 2,
      payload: %Ash.Union{type: :deposited, value: %Vault.Ledger.Payloads.Deposited{amount_cents: 500}},
      recorded_at: DateTime.utc_now()
    }
    {:ok, state} = Fold.apply_event(state, e2)
    assert!(state.balance_cents == 1500, "balance 1500")
    assert!(state.deposit_count == 1, "deposit count 1")
    assert!(state.version == 2, "version 2")

    # 4. Event Apply - Withdrawn
    e3 = %Event{
      account_id: "acc_1",
      version: 3,
      sequence: 3,
      payload: %Ash.Union{type: :withdrawn, value: %Vault.Ledger.Payloads.Withdrawn{amount_cents: 300}},
      recorded_at: DateTime.utc_now()
    }
    {:ok, state} = Fold.apply_event(state, e3)
    assert!(state.balance_cents == 1200, "balance 1200")
    assert!(state.withdrawal_count == 1, "withdrawal count 1")
    assert!(state.version == 3, "version 3")

    # 5. Rejects - Account Mismatch
    bad_acc_event = %Event{account_id: "acc_2", version: 4, sequence: 4}
    assert!(Fold.apply_event(state, bad_acc_event) == {:error, {:account_mismatch, "acc_1", "acc_2"}}, "account mismatch")

    # 6. Rejects - Version Gap
    bad_version_event = %Event{account_id: "acc_1", version: 5, sequence: 4}
    assert!(Fold.apply_event(state, bad_version_event) == {:error, {:version_gap, 4, 5}}, "version gap")

    # 7. Replay
    {:ok, replayed} = Fold.replay(Fold.initial("acc_1"), [e1, e2, e3])
    assert!(replayed.balance_cents == 1200, "replay balance")
    assert!(replayed.version == 3, "replay version")

    # 8. Replay - Out of order
    assert!(Fold.replay(Fold.initial("acc_1"), [e1, e3, e2]) == {:error, {:out_of_order, 2}}, "replay out of order")

    IO.puts("Pure fold logic validated successfully.")
  end

  def test_append_and_store_contracts do
    IO.puts("\n--- Testing Event Store Append and Contracts ---")

    # Clear Event table (private table scoped to process, already empty but good practice)
    # Append first event
    payload = %{"type" => "account_opened", "owner" => "Alice", "opening_balance_cents" => 1000}
    {:ok, e1} = Ledger.append_event(%{
      account_id: "acc_store_1",
      version: 1,
      payload: payload,
      recorded_at: DateTime.utc_now()
    })

    assert!(e1.sequence == 1, "first event sequence should be 1")
    assert!(e1.version == 1, "first event version should be 1")

    # Append second event
    payload2 = %{"type" => "deposited", "amount_cents" => 200}
    {:ok, e2} = Ledger.append_event(%{
      account_id: "acc_store_1",
      version: 2,
      payload: payload2,
      recorded_at: DateTime.utc_now()
    })
    assert!(e2.sequence == 2, "second event sequence should be 2")
    assert!(e2.version == 2, "second event version should be 2")

    # Reject sequence input
    assert_error!(fn ->
      Ledger.append_event!(%{
        account_id: "acc_store_1",
        version: 3,
        sequence: 99,
        payload: payload2,
        recorded_at: DateTime.utc_now()
      })
    end, Ash.Error.Invalid.NoSuchInput, nil, nil) # wait, NoSuchInput isn't an InvalidAttribute or InvalidChanges, it's NoSuchInput which has no field/message directly on inner, but it is of class :invalid. We just want to make sure it raises.

    # Version already present check
    assert_error!(fn ->
      Ledger.append_event!(%{
        account_id: "acc_store_1",
        version: 2,
        payload: payload2,
        recorded_at: DateTime.utc_now()
      })
    end, Ash.Error.Changes.InvalidChanges, [:account_id, :version], "has already been taken")

    # Version gap check (version too high)
    assert_error!(fn ->
      Ledger.append_event!(%{
        account_id: "acc_store_1",
        version: 4,
        payload: payload2,
        recorded_at: DateTime.utc_now()
      })
    end, Ash.Error.Changes.InvalidAttribute, :version, "version must be exactly one greater than the current stream version")

    # Version gap check (version too low)
    assert_error!(fn ->
      Ledger.append_event!(%{
        account_id: "acc_store_1",
        version: 0,
        payload: payload2,
        recorded_at: DateTime.utc_now()
      })
    end, Ash.Error.Changes.InvalidAttribute, :version, "version must be exactly one greater than the current stream version")

    # Immutability: no update or destroy actions
    assert_error!(fn ->
      Ash.destroy!(e1)
    end, Ash.Error.Invalid.NoPrimaryAction, nil, nil)

    assert_error!(fn ->
      Ash.update!(e1, %{account_id: "mutated"})
    end, RuntimeError, nil, nil)

    IO.puts("Event store append and contracts validated successfully.")
  end

  def test_commands_and_invariants do
    IO.puts("\n--- Testing Commands and Invariant Precedence ---")

    # Clear ETS store by deleting all events, snapshots, projections, checkpoints
    # (Since this is private to process, we can just use new account_ids to stay isolated)
    acc = "acc_cmd_1"

    # Invariant 1: amount_cents is not positive
    assert_error!(fn ->
      Ledger.deposit!(acc, 0)
    end, Ash.Error.Action.InvalidArgument, :amount_cents, "amount must be positive")

    # Invariant 2: opening_balance_cents is negative
    assert_error!(fn ->
      Ledger.open_account!(acc, "Alice", %{opening_balance_cents: -50})
    end, Ash.Error.Action.InvalidArgument, :opening_balance_cents, "opening balance must not be negative")

    # Invariant 3: transfer source and destination are the same
    assert_error!(fn ->
      Ledger.transfer!(acc, acc, 100)
    end, Ash.Error.Action.InvalidArgument, :to_account_id, "cannot transfer to the same account")

    # Invariant 5: account does not exist (any command other than open_account)
    assert_error!(fn ->
      Ledger.deposit!(acc, 100)
    end, Ash.Error.Action.InvalidArgument, :account_id, "account does not exist")

    # Now open account successfully
    {:ok, res1} = Ledger.open_account(acc, "Alice", %{opening_balance_cents: 1000})
    assert!(res1.command == :open_account, "command name")
    assert!(res1.account_id == acc, "account_id")
    assert!(length(res1.appended) == 1, "appended events")
    assert!(res1.state.balance_cents == 1000, "state balance")

    # Invariant 4: open_account for an account that already has events
    assert_error!(fn ->
      Ledger.open_account!(acc, "Bob")
    end, Ash.Error.Action.InvalidArgument, :account_id, "account already exists")

    # Deposit successfully
    {:ok, res2} = Ledger.deposit(acc, 500)
    assert!(res2.state.balance_cents == 1500, "balance after deposit")

    # Withdraw successfully
    {:ok, res3} = Ledger.withdraw(acc, 300)
    assert!(res3.state.balance_cents == 1200, "balance after withdraw")

    # Invariant 9: withdrawal larger than the balance
    assert_error!(fn ->
      Ledger.withdraw!(acc, 2000)
    end, Ash.Error.Action.InvalidArgument, :amount_cents, "insufficient funds")

    # Freeze successfully
    {:ok, res4} = Ledger.freeze_account(acc, :fraud_review)
    assert!(res4.state.status == :frozen, "status after freeze")

    # Invariant 6: account is frozen
    assert_error!(fn ->
      Ledger.deposit!(acc, 100)
    end, Ash.Error.Action.InvalidArgument, :account_id, "account is frozen")

    assert_error!(fn ->
      Ledger.withdraw!(acc, 100)
    end, Ash.Error.Action.InvalidArgument, :account_id, "account is frozen")

    # Invariant 7: freeze on account that is not open (currently frozen)
    assert_error!(fn ->
      Ledger.freeze_account!(acc, :chargeback)
    end, Ash.Error.Action.InvalidArgument, :account_id, "account is not open")

    # Unfreeze successfully
    {:ok, res5} = Ledger.unfreeze_account(acc, %{note: "resolved"})
    assert!(res5.state.status == :open, "status after unfreeze")

    # Invariant 8: unfreeze on account that is not frozen
    assert_error!(fn ->
      Ledger.unfreeze_account!(acc)
    end, Ash.Error.Action.InvalidArgument, :account_id, "account is not frozen")

    # Transfer test
    acc2 = "acc_cmd_2"
    Ledger.open_account!(acc2, "Bob", %{opening_balance_cents: 500})
    
    {:ok, res_tx} = Ledger.transfer(acc, acc2, 400)
    assert!(res_tx.command == :transfer, "command name")
    assert!(res_tx.account_id == acc, "primary account should be source")
    assert!(length(res_tx.appended) == 2, "should append two events")
    assert!(res_tx.state.balance_cents == 800, "source balance should decrease")

    # Destination balance check
    {:ok, dest_state} = Aggregate.current(acc2)
    assert!(dest_state.balance_cents == 900, "destination balance should increase")

    IO.puts("Commands and invariant precedence validated successfully.")
  end

  def test_snapshots do
    IO.puts("\n--- Testing Snapshots ---")

    acc = "acc_snap_1"
    # Open account
    Ledger.open_account!(acc, "Alice", %{opening_balance_cents: 1000})
    # Do 4 deposits to reach version 5 (automatic snapshot trigger)
    Ledger.deposit!(acc, 100) # version 2
    Ledger.deposit!(acc, 100) # version 3
    Ledger.deposit!(acc, 100) # version 4
    Ledger.deposit!(acc, 100) # version 5

    # Check if snapshot for version 5 exists
    {:ok, snap} = Snapshots.latest(acc)
    assert!(snap.version == 5, "latest snapshot should be version 5")
    assert!(snap.account_id == acc, "snapshot account_id")

    # Verify snapshot
    assert!(Snapshots.verify(snap) == :ok, "snapshot verification should pass")

    # Test dump and restore
    state = Snapshots.restore(snap.state)
    assert!(state.account_id == acc, "restored account_id")
    assert!(state.version == 5, "restored version")
    assert!(state.balance_cents == 1400, "restored balance")

    # Test verification failure (corrupt checksum)
    corrupt_checksum_snap = %{snap | checksum: "invalid_checksum"}
    assert!(Snapshots.verify(corrupt_checksum_snap) == {:error, :checksum_mismatch}, "checksum mismatch")

    # Test verification failure (corrupt version)
    corrupt_version_snap = %{snap | version: 4}
    assert!(Snapshots.verify(corrupt_version_snap) == {:error, :version_mismatch}, "version mismatch")

    IO.puts("Snapshots validated successfully.")
  end

  def test_aggregate_reconstruction do
    IO.puts("\n--- Testing Aggregate Reconstruction ---")

    acc = "acc_recon_1"
    Ledger.open_account!(acc, "Alice", %{opening_balance_cents: 1000})
    Enum.each(1..9, fn _ -> Ledger.deposit!(acc, 100) end) # reach version 10

    # There should be snapshots for version 5 and 10
    {:ok, snap10} = Snapshots.latest(acc)
    assert!(snap10.version == 10, "latest snapshot should be version 10")

    # fold_all: full fold ignoring snapshots
    {:ok, state_fold_all} = Aggregate.fold_all(acc)
    assert!(state_fold_all.version == 10, "fold_all version")
    assert!(state_fold_all.balance_cents == 1900, "fold_all balance")

    # current: accelerated using snapshots
    {:ok, state_current} = Aggregate.current(acc)
    assert!(state_current.version == 10, "current version")
    assert!(state_current.balance_cents == 1900, "current balance")

    # Corrupt the latest snapshot (version 10) in the DB
    Ash.update!(snap10, %{checksum: "corrupt"})

    # current should still succeed by falling back to version 5 snapshot, or full fold
    {:ok, state_fallback} = Aggregate.current(acc)
    assert!(state_fallback.version == 10, "current fallback version")
    assert!(state_fallback.balance_cents == 1900, "current fallback balance")

    IO.puts("Aggregate reconstruction validated successfully.")
  end

  def test_projector_and_rebuild do
    IO.puts("\n--- Testing Projector and Rebuild ---")

    acc = "acc_proj_1"
    Ledger.open_account!(acc, "Alice", %{opening_balance_cents: 1000})
    Ledger.deposit!(acc, 500)

    # Read model should be fully up to date after commands
    IO.inspect(Ash.read!(Vault.Ledger.AccountProjection), label: "ALL PROJECTIONS")
    {:ok, proj} = Ash.get(AccountProjection, acc)
    assert!(proj.balance_cents == 1500, "projection balance")
    assert!(proj.version == 2, "projection version")

    # Checkpoint should be up to the newest sequence
    # Let's find the highest sequence
    [latest_event] = Ash.read!(Ash.Query.sort(Event, sequence: :desc) |> Ash.Query.limit(1))
    assert!(Projector.checkpoint() == latest_event.sequence, "checkpoint matches latest event sequence")

    # Modify projection behind projector's back
    Ash.update!(proj, %{balance_cents: 9999})
    {:ok, modified_proj} = Ash.get(AccountProjection, acc)
    assert!(modified_proj.balance_cents == 9999, "modified projection")

    # Rebuild all
    Vault.Ledger.Hook.clear(:after_load)
    {:ok, rebuild_res} = Projector.rebuild_all()
    assert!(rebuild_res.checkpoint == latest_event.sequence, "rebuild checkpoint")

    # Hook must have run exactly once
    assert!(Vault.Ledger.Hook.count(:after_load) == 1, "after_load hook count")

    # Projection should be restored to correct value!
    {:ok, restored_proj} = Ash.get(AccountProjection, acc)
    assert!(restored_proj.balance_cents == 1500, "restored projection balance after rebuild")

    # Test state_at
    {:ok, state_v1} = Projector.state_at(acc, {:version, 1})
    assert!(state_v1.version == 1, "state_at version 1")
    assert!(state_v1.balance_cents == 1000, "state_at balance 1000")

    {:ok, state_v0} = Projector.state_at(acc, {:version, 0})
    assert!(state_v0.version == 0, "state_at version 0")
    assert!(state_v0.status == :absent, "state_at status absent")

    # Test audit
    diffs = Projector.audit(acc)
    assert!(length(diffs) == 2, "audit length")
    [d1, d2] = diffs
    assert!(d1.version == 1, "audit 1 version")
    assert!(d1.balance_before == 0, "audit 1 before")
    assert!(d1.balance_after == 1000, "audit 1 after")
    assert!(d1.delta_cents == 1000, "audit 1 delta")

    assert!(d2.version == 2, "audit 2 version")
    assert!(d2.balance_before == 1000, "audit 2 before")
    assert!(d2.balance_after == 1500, "audit 2 after")
    assert!(d2.delta_cents == 500, "audit 2 delta")

    IO.puts("Projector and rebuild validated successfully.")
  end
end

TestLedger.run_tests()
