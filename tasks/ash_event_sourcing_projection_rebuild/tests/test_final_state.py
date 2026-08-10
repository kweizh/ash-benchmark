"""Final-state verification for the ash_event_sourcing_projection_rebuild task.

The whole contract is exercised by a self-contained ExUnit suite that is written to
/tmp at verification time and executed with `mix run` from the project root. The
suite prints one `@@HARBOR@@<name>@@<status>@@<base64 detail>` line per scenario,
which is parsed here so that every behaviour is reported as its own pytest case.

Every reference to a module the executor must write goes through `Module.concat/1`,
so the suite still compiles (and reports clean failures) against an unsolved project.
"""

import base64
import os
import subprocess

import pytest

PROJECT_DIR = "/home/user/vault"
SUITE_PATH = "/tmp/harbor_event_sourcing_final.exs"

SCENARIOS = [
    ("T01", "T01 event resource declares the append only log schema"),
    ("T02", "T02 the log is immutable"),
    ("T03", "T03 the global sequence cannot be supplied by the caller"),
    ("T04", "T04 sequences are globally contiguous and versions are per stream"),
    ("T05", "T05 a duplicate stream position is rejected by the identity"),
    ("T06", "T06 a version gap is rejected and consumes no sequence number"),
    ("T07", "T07 every payload member round trips through the store"),
    ("T08", "T08 each payload member enforces its own constraints"),
    ("T09", "T09 an unrecognised payload tag is rejected"),
    ("T10", "T10 the payload type is a union new type with the five documented members"),
    ("T11", "T11 the initial state is the documented zero value"),
    ("T12", "T12 applying each event type produces the documented state"),
    ("T13", "T13 structural checks take precedence over business rules"),
    ("T14", "T14 business rules reject impossible transitions"),
    ("T15", "T15 an unknown event type is reported by name"),
    ("T16", "T16 replay folds a tail and surfaces the first failure"),
    ("T17", "T17 replay rejects out of order input instead of sorting it"),
    ("T18", "T18 the fold performs no storage access"),
    ("T19", "T19 opening an account returns the documented command result"),
    ("T20", "T20 deposits and withdrawals advance the stream"),
    ("T21", "T21 a transfer appends two events with consecutive sequences"),
    ("T22", "T22 a rejected transfer leaves no trace"),
    ("T23", "T23 every invariant violation reports the documented field and message"),
    ("T24", "T24 freezing blocks money movement until the account is unfrozen"),
    ("T25", "T25 an omitted recorded_at falls back to the current time"),
    ("T26", "T26 commands are generic actions returning the command result struct"),
    ("T27", "T27 snapshot serialisation is exact and round trips"),
    ("T28", "T28 the checksum covers exactly the documented fields"),
    ("T29", "T29 commands snapshot every fifth version"),
    ("T30", "T30 direct appends never create a snapshot"),
    ("T31", "T31 snapshot verification detects tampering"),
    ("T32", "T32 the current state is reconstructed from the newest valid snapshot"),
    ("T33", "T33 a newer snapshot supersedes an older one"),
    ("T34", "T34 a corrupt snapshot is ignored rather than trusted"),
    ("T35", "T35 commands keep the read model up to date"),
    ("T36", "T36 direct appends only reach the read model through catch up"),
    ("T37", "T37 catch up is idempotent"),
    ("T38", "T38 a full rebuild reproduces the incrementally maintained rows"),
    ("T39", "T39 a rebuild repairs a projection row edited behind its back"),
    ("T40", "T40 a rebuild recreates a deleted projection row"),
    ("T41", "T41 rebuilding an empty log clears the read model"),
    ("T42", "T42 events appended during a rebuild belong to the next catch up"),
    ("T43", "T43 an unfoldable event halts the projection at the last good sequence"),
    ("T44", "T44 time travel and the audit trail"),
]

SUITE_SOURCE = r"""
defmodule HarborFormatter do
  @moduledoc false
  use GenServer

  def init(_opts), do: {:ok, %{}}

  def handle_cast({:test_finished, %ExUnit.Test{} = test}, state) do
    status =
      case test.state do
        nil -> "pass"
        {:excluded, _} -> "skip"
        {:skipped, _} -> "skip"
        _ -> "fail"
      end

    detail =
      case test.state do
        {:failed, failures} ->
          try do
            ExUnit.Formatter.format_test_failure(test, failures, 1, 120, fn _, msg -> msg end)
          rescue
            _ -> inspect(failures)
          end

        {kind, reason} ->
          inspect({kind, reason})

        _ ->
          ""
      end

    IO.puts("@@HARBOR@@#{test.name}@@#{status}@@#{Base.encode64(detail)}")
    {:noreply, state}
  end

  def handle_cast(_event, state), do: {:noreply, state}
end

defmodule H do
  @moduledoc false

  @ledger Module.concat(["Vault", "Ledger"])
  @event Module.concat(["Vault", "Ledger", "Event"])
  @snapshot Module.concat(["Vault", "Ledger", "Snapshot"])
  @projection Module.concat(["Vault", "Ledger", "AccountProjection"])
  @checkpoint Module.concat(["Vault", "Ledger", "Checkpoint"])
  @fold Module.concat(["Vault", "Ledger", "Fold"])
  @aggregate Module.concat(["Vault", "Ledger", "Aggregate"])
  @snapshots Module.concat(["Vault", "Ledger", "Snapshots"])
  @projector Module.concat(["Vault", "Ledger", "Projector"])
  @account_state Module.concat(["Vault", "Ledger", "AccountState"])
  @command_result Module.concat(["Vault", "Ledger", "CommandResult"])
  @payload Module.concat(["Vault", "Ledger", "Payload"])
  @hook Module.concat(["Vault", "Ledger", "Hook"])

  @payload_mods %{
    account_opened: Module.concat(["Vault", "Ledger", "Payloads", "AccountOpened"]),
    deposited: Module.concat(["Vault", "Ledger", "Payloads", "Deposited"]),
    withdrawn: Module.concat(["Vault", "Ledger", "Payloads", "Withdrawn"]),
    frozen: Module.concat(["Vault", "Ledger", "Payloads", "Frozen"]),
    unfrozen: Module.concat(["Vault", "Ledger", "Payloads", "Unfrozen"])
  }

  def ledger, do: @ledger
  def event, do: @event
  def snapshot, do: @snapshot
  def projection, do: @projection
  def checkpoint_resource, do: @checkpoint
  def account_state, do: @account_state
  def command_result, do: @command_result
  def payload, do: @payload
  def hook, do: @hook
  def payload_mod(name), do: Map.fetch!(@payload_mods, name)
  def payload_mods, do: @payload_mods

  def t(n), do: DateTime.add(~U[2026-03-01 10:00:00.000000Z], n, :second)

  # -- command interface ----------------------------------------------------

  def open(id, owner, params \\ %{}), do: apply(@ledger, :open_account, [id, owner, params])
  def open!(id, owner, params \\ %{}), do: apply(@ledger, :open_account!, [id, owner, params])
  def deposit(id, amount, params \\ %{}), do: apply(@ledger, :deposit, [id, amount, params])
  def deposit!(id, amount, params \\ %{}), do: apply(@ledger, :deposit!, [id, amount, params])
  def withdraw(id, amount, params \\ %{}), do: apply(@ledger, :withdraw, [id, amount, params])
  def withdraw!(id, amount, params \\ %{}), do: apply(@ledger, :withdraw!, [id, amount, params])

  def transfer(from, to, amount, params \\ %{}),
    do: apply(@ledger, :transfer, [from, to, amount, params])

  def transfer!(from, to, amount, params \\ %{}),
    do: apply(@ledger, :transfer!, [from, to, amount, params])

  def freeze(id, reason, params \\ %{}), do: apply(@ledger, :freeze_account, [id, reason, params])

  def freeze!(id, reason, params \\ %{}),
    do: apply(@ledger, :freeze_account!, [id, reason, params])

  def unfreeze(id, params \\ %{}), do: apply(@ledger, :unfreeze_account, [id, params])
  def unfreeze!(id, params \\ %{}), do: apply(@ledger, :unfreeze_account!, [id, params])

  def append(attrs), do: apply(@ledger, :append_event, [attrs])
  def append!(attrs), do: apply(@ledger, :append_event!, [attrs])

  # -- store readers --------------------------------------------------------

  def events, do: @ledger |> apply(:list_events!, []) |> Enum.sort_by(& &1.sequence)
  def events_for(id), do: Enum.filter(events(), &(&1.account_id == id))
  def snapshots, do: @snapshot |> Ash.read!() |> Enum.sort_by(&{&1.account_id, &1.version})
  def rows, do: @projection |> Ash.read!() |> Enum.sort_by(& &1.account_id)
  def row(id), do: Enum.find(rows(), &(&1.account_id == id))

  @row_fields [
    :account_id,
    :owner,
    :balance_cents,
    :status,
    :version,
    :deposit_count,
    :withdrawal_count,
    :last_event_sequence,
    :last_recorded_at
  ]

  def row_fields, do: @row_fields
  def row_map(nil), do: nil
  def row_map(record), do: Map.take(record, @row_fields)
  def row_maps, do: Enum.map(rows(), &row_map/1)

  # -- solution api ---------------------------------------------------------

  def checkpoint, do: apply(@projector, :checkpoint, [])
  def catch_up, do: apply(@projector, :catch_up, [])
  def rebuild, do: apply(@projector, :rebuild_all, [])
  def state_at(id, point), do: apply(@projector, :state_at, [id, point])
  def audit(id), do: apply(@projector, :audit, [id])

  def fold_all(id), do: apply(@aggregate, :fold_all, [id])
  def current(id), do: apply(@aggregate, :current, [id])

  def initial(id), do: apply(@fold, :initial, [id])
  def apply_event(state, event), do: apply(@fold, :apply_event, [state, event])
  def replay(state, events), do: apply(@fold, :replay, [state, events])

  def interval, do: apply(@snapshots, :interval, [])
  def dump(state), do: apply(@snapshots, :dump, [state])
  def restore(map), do: apply(@snapshots, :restore, [map])
  def checksum(state), do: apply(@snapshots, :checksum, [state])
  def latest(id), do: apply(@snapshots, :latest, [id])
  def verify(snapshot), do: apply(@snapshots, :verify, [snapshot])

  # -- builders -------------------------------------------------------------

  def mkstate(fields \\ %{}), do: struct(@account_state, fields)

  def mkevent(fields), do: struct(@event, fields)

  def union(type, fields \\ %{}) do
    %Ash.Union{
      type: type,
      value: struct(payload_mod(type), Map.put(fields, :type, Atom.to_string(type)))
    }
  end

  def hand_event(account_id, version, sequence, type, fields \\ %{}, at \\ nil) do
    mkevent(%{
      id: "hand-#{account_id}-#{version}",
      account_id: account_id,
      version: version,
      sequence: sequence,
      payload: union(type, fields),
      recorded_at: at || t(version)
    })
  end

  def expected_checksum(state) do
    canonical =
      Enum.join(
        [
          state.account_id,
          state.version,
          state.balance_cents,
          Atom.to_string(state.status),
          state.deposit_count,
          state.withdrawal_count
        ],
        "|"
      )

    :sha256 |> :crypto.hash(canonical) |> Base.encode16(case: :lower)
  end

  def error_of({:error, %Ash.Error.Invalid{errors: [error]}}), do: error
  def error_of({:error, %Ash.Error.Invalid{errors: errors}}), do: hd(errors)
  def error_of({:error, error}), do: error
  def error_of(other), do: other

  def payload_map(:account_opened, owner, amount),
    do: %{"type" => "account_opened", "owner" => owner, "opening_balance_cents" => amount}

  def payload_map(:deposited, amount),
    do: %{"type" => "deposited", "amount_cents" => amount}

  def payload_map(:withdrawn, amount),
    do: %{"type" => "withdrawn", "amount_cents" => amount}
end

ExUnit.start(
  autorun: false,
  formatters: [HarborFormatter],
  seed: 0,
  colors: [enabled: false],
  timeout: 120_000
)

defmodule EventSourcingProjectionTest do
  use ExUnit.Case, async: false

  # ==========================================================================
  # Event store and immutability
  # ==========================================================================

  test "T01 event resource declares the append only log schema" do
    res = H.event()

    assert Ash.Resource.Info.data_layer(res) == Ash.DataLayer.Ets,
           "Vault.Ledger.Event must use the ETS data layer"

    assert Ash.DataLayer.Ets.Info.private?(res) == true,
           "Vault.Ledger.Event must use private ETS tables"

    assert Ash.Resource.Info.domain(res) == H.ledger()
    assert Ash.Resource.Info.primary_key(res) == [:id]

    for {name, type} <- [
          {:sequence, Ash.Type.Integer},
          {:account_id, Ash.Type.String},
          {:version, Ash.Type.Integer},
          {:recorded_at, Ash.Type.UtcDatetimeUsec},
          {:payload, H.payload()}
        ] do
      attribute = Ash.Resource.Info.attribute(res, name)
      assert attribute, "Vault.Ledger.Event is missing the #{name} attribute"
      assert attribute.type == type, "#{name} has the wrong type: #{inspect(attribute.type)}"
      assert attribute.allow_nil? == false, "#{name} must be required"
    end

    identities = Ash.Resource.Info.identities(res)
    keysets = Enum.map(identities, &Enum.sort(&1.keys))
    assert Enum.sort([:account_id, :version]) in keysets
    assert [:sequence] in keysets

    for identity <- identities do
      assert identity.pre_check_with != nil,
             "identity #{identity.name} must declare pre_check_with"
    end

    assert Ash.Resource.Info.primary_action(res, :read) != nil
  end

  test "T02 the log is immutable" do
    actions = Ash.Resource.Info.actions(H.event())
    mutating = Enum.filter(actions, &(&1.type in [:update, :destroy]))

    assert mutating == [],
           "Vault.Ledger.Event must not declare update/destroy actions, found: " <>
             inspect(Enum.map(mutating, & &1.name))

    event =
      H.append!(%{
        account_id: "A",
        version: 1,
        payload: H.payload_map(:account_opened, "Ada", 100),
        recorded_at: H.t(1)
      })

    assert {:error, %Ash.Error.Invalid{errors: errors}} = Ash.destroy(event)

    assert Enum.any?(errors, &match?(%Ash.Error.Invalid.NoPrimaryAction{type: :destroy}, &1)),
           "expected a NoPrimaryAction(:destroy) error, got #{inspect(errors)}"

    update_outcome =
      try do
        Ash.update(event, %{})
      rescue
        error -> {:raised, error}
      catch
        kind, reason -> {:caught, kind, reason}
      end

    refute match?({:ok, _}, update_outcome),
           "updating a stored event must fail, got #{inspect(update_outcome)}"

    assert length(H.events()) == 1
    assert hd(H.events()).account_id == "A"
  end

  test "T03 the global sequence cannot be supplied by the caller" do
    outcome =
      H.append(%{
        account_id: "A",
        version: 1,
        sequence: 9,
        payload: H.payload_map(:account_opened, "Ada", 0),
        recorded_at: H.t(1)
      })

    assert %Ash.Error.Invalid.NoSuchInput{input: :sequence} = H.error_of(outcome)
    assert H.events() == []
  end

  test "T04 sequences are globally contiguous and versions are per stream" do
    H.open!("A", "Ada", %{opening_balance_cents: 1000, recorded_at: H.t(1)})
    H.deposit!("A", 100, %{recorded_at: H.t(2)})
    H.deposit!("A", 100, %{recorded_at: H.t(3)})
    H.open!("B", "Bo", %{recorded_at: H.t(4)})
    H.deposit!("B", 50, %{recorded_at: H.t(5)})

    events = H.events()
    assert Enum.map(events, & &1.sequence) == [1, 2, 3, 4, 5]

    assert Enum.map(events, &{&1.account_id, &1.version}) == [
             {"A", 1},
             {"A", 2},
             {"A", 3},
             {"B", 1},
             {"B", 2}
           ]

    assert Enum.map(H.events_for("A"), & &1.version) == [1, 2, 3]
    assert Enum.map(H.events_for("B"), & &1.version) == [1, 2]
  end

  test "T05 a duplicate stream position is rejected by the identity" do
    H.append!(%{
      account_id: "A",
      version: 1,
      payload: H.payload_map(:account_opened, "Ada", 0),
      recorded_at: H.t(1)
    })

    outcome =
      H.append(%{
        account_id: "A",
        version: 1,
        payload: H.payload_map(:deposited, 5),
        recorded_at: H.t(2)
      })

    error = H.error_of(outcome)

    assert %Ash.Error.Changes.InvalidChanges{} = error
    assert error.fields == [:account_id, :version]
    assert error.message == "has already been taken"
    assert length(H.events()) == 1
  end

  test "T06 a version gap is rejected and consumes no sequence number" do
    H.append!(%{
      account_id: "A",
      version: 1,
      payload: H.payload_map(:account_opened, "Ada", 0),
      recorded_at: H.t(1)
    })

    for bad_version <- [3, 0, -2] do
      error =
        H.error_of(
          H.append(%{
            account_id: "A",
            version: bad_version,
            payload: H.payload_map(:deposited, 5),
            recorded_at: H.t(2)
          })
        )

      assert %Ash.Error.Changes.InvalidAttribute{} = error
      assert error.field == :version

      assert error.message ==
               "version must be exactly one greater than the current stream version"

      assert error.vars[:expected] == 2
    end

    assert length(H.events()) == 1

    accepted =
      H.append!(%{
        account_id: "A",
        version: 2,
        payload: H.payload_map(:deposited, 5),
        recorded_at: H.t(2)
      })

    assert accepted.sequence == 2
  end

  test "T07 every payload member round trips through the store" do
    specs = [
      {"P1", %{"type" => "account_opened", "owner" => "Ada", "opening_balance_cents" => 700},
       :account_opened},
      {"P2", %{"type" => "deposited", "amount_cents" => 500}, :deposited},
      {"P3", %{"type" => "withdrawn", "amount_cents" => 250}, :withdrawn},
      {"P4", %{"type" => "frozen", "reason" => "chargeback"}, :frozen},
      {"P5", %{"type" => "unfrozen", "note" => "cleared"}, :unfrozen}
    ]

    for {account, map, _type} <- specs do
      H.append!(%{account_id: account, version: 1, payload: map, recorded_at: H.t(1)})
    end

    by_account = Map.new(H.events(), &{&1.account_id, &1})

    for {account, _map, type} <- specs do
      event = Map.fetch!(by_account, account)
      assert %Ash.Union{type: ^type} = event.payload
      assert event.payload.value.__struct__ == H.payload_mod(type)
    end

    assert by_account["P1"].payload.value.owner == "Ada"
    assert by_account["P1"].payload.value.opening_balance_cents == 700
    assert by_account["P2"].payload.value.amount_cents == 500
    assert by_account["P3"].payload.value.amount_cents == 250
    assert by_account["P4"].payload.value.reason == :chargeback
    assert by_account["P5"].payload.value.note == "cleared"
  end

  test "T08 each payload member enforces its own constraints" do
    cases = [
      {%{"type" => "deposited", "amount_cents" => 0}, :amount_cents},
      {%{"type" => "withdrawn", "amount_cents" => -5}, :amount_cents},
      {%{"type" => "account_opened", "owner" => "", "opening_balance_cents" => 0}, :owner},
      {%{"type" => "account_opened", "owner" => "Ada", "opening_balance_cents" => -1},
       :opening_balance_cents},
      {%{"type" => "frozen", "reason" => "nope"}, :reason},
      {%{"type" => "unfrozen", "note" => String.duplicate("x", 200)}, :note}
    ]

    for {map, field} <- cases do
      error = H.error_of(H.append(%{account_id: "A", version: 1, payload: map, recorded_at: H.t(1)}))

      assert Map.get(error, :field) == field,
             "expected payload #{inspect(map)} to be rejected on #{inspect(field)}, got #{inspect(error)}"
    end

    assert H.events() == []
  end

  test "T09 an unrecognised payload tag is rejected" do
    error =
      H.error_of(
        H.append(%{
          account_id: "A",
          version: 1,
          payload: %{"type" => "teleported", "amount_cents" => 1},
          recorded_at: H.t(1)
        })
      )

    assert Map.get(error, :field) == :payload
    assert Map.get(error, :message) =~ "No union type matched"
    assert H.events() == []
  end

  test "T10 the payload type is a union new type with the five documented members" do
    assert Ash.Type.NewType.subtype_of(H.payload()) == Ash.Type.Union

    types = Ash.Resource.Info.attribute(H.event(), :payload).constraints[:types]
    assert types, "the payload attribute exposes no union member configuration"

    assert Enum.sort(Keyword.keys(types)) ==
             Enum.sort([:account_opened, :deposited, :withdrawn, :frozen, :unfrozen])

    for {name, module} <- H.payload_mods() do
      assert types[name][:type] == module,
             "union member #{name} must be backed by #{inspect(module)}"
    end
  end

  # ==========================================================================
  # Fold
  # ==========================================================================

  test "T11 the initial state is the documented zero value" do
    state = H.initial("A")
    assert state.__struct__ == H.account_state()
    assert state.account_id == "A"
    assert state.owner == nil
    assert state.balance_cents == 0
    assert state.status == :absent
    assert state.version == 0
    assert state.deposit_count == 0
    assert state.withdrawal_count == 0
    assert state.last_event_type == nil
    assert state.last_recorded_at == nil
  end

  test "T12 applying each event type produces the documented state" do
    s0 = H.initial("A")

    assert {:ok, s1} =
             H.apply_event(
               s0,
               H.hand_event("A", 1, 1, :account_opened, %{
                 owner: "Ada",
                 opening_balance_cents: 1000
               })
             )

    assert {s1.owner, s1.balance_cents, s1.status, s1.version} == {"Ada", 1000, :open, 1}
    assert s1.last_event_type == :account_opened
    assert s1.last_recorded_at == H.t(1)

    assert {:ok, s2} = H.apply_event(s1, H.hand_event("A", 2, 2, :deposited, %{amount_cents: 250}))
    assert {s2.balance_cents, s2.deposit_count, s2.withdrawal_count} == {1250, 1, 0}
    assert s2.last_event_type == :deposited

    assert {:ok, s3} = H.apply_event(s2, H.hand_event("A", 3, 3, :withdrawn, %{amount_cents: 400}))
    assert {s3.balance_cents, s3.deposit_count, s3.withdrawal_count} == {850, 1, 1}

    assert {:ok, s4} = H.apply_event(s3, H.hand_event("A", 4, 4, :frozen, %{reason: :court_order}))
    assert s4.status == :frozen
    assert s4.balance_cents == 850

    assert {:ok, s5} = H.apply_event(s4, H.hand_event("A", 5, 5, :unfrozen, %{note: "cleared"}))
    assert s5.status == :open
    assert s5.version == 5
    assert s5.last_event_type == :unfrozen
    assert s5.owner == "Ada"
  end

  test "T13 structural checks take precedence over business rules" do
    {:ok, s1} =
      H.apply_event(
        H.initial("A"),
        H.hand_event("A", 1, 1, :account_opened, %{owner: "Ada", opening_balance_cents: 10})
      )

    assert {:error, {:account_mismatch, "A", "B"}} =
             H.apply_event(s1, H.hand_event("B", 5, 5, :deposited, %{amount_cents: 1}))

    assert {:error, {:version_gap, 2, 3}} =
             H.apply_event(s1, H.hand_event("A", 3, 3, :deposited, %{amount_cents: 1}))

    assert {:error, {:version_gap, 2, 1}} =
             H.apply_event(s1, H.hand_event("A", 1, 1, :deposited, %{amount_cents: 1}))
  end

  test "T14 business rules reject impossible transitions" do
    s0 = H.initial("A")

    assert {:error, :account_absent} =
             H.apply_event(s0, H.hand_event("A", 1, 1, :deposited, %{amount_cents: 5}))

    assert {:error, :account_absent} =
             H.apply_event(s0, H.hand_event("A", 1, 1, :withdrawn, %{amount_cents: 5}))

    assert {:error, :not_frozen} =
             H.apply_event(s0, H.hand_event("A", 1, 1, :unfrozen, %{note: nil}))

    assert {:error, :not_open} =
             H.apply_event(s0, H.hand_event("A", 1, 1, :frozen, %{reason: :fraud_review}))

    {:ok, s1} =
      H.apply_event(
        s0,
        H.hand_event("A", 1, 1, :account_opened, %{owner: "Ada", opening_balance_cents: 100})
      )

    assert {:error, :already_open} =
             H.apply_event(
               s1,
               H.hand_event("A", 2, 2, :account_opened, %{owner: "Bo", opening_balance_cents: 1})
             )

    assert {:error, :insufficient_funds} =
             H.apply_event(s1, H.hand_event("A", 2, 2, :withdrawn, %{amount_cents: 101}))

    assert {:ok, exact} =
             H.apply_event(s1, H.hand_event("A", 2, 2, :withdrawn, %{amount_cents: 100}))

    assert exact.balance_cents == 0

    {:ok, frozen} =
      H.apply_event(s1, H.hand_event("A", 2, 2, :frozen, %{reason: :fraud_review}))

    assert {:error, :account_frozen} =
             H.apply_event(frozen, H.hand_event("A", 3, 3, :deposited, %{amount_cents: 5}))

    assert {:error, :account_frozen} =
             H.apply_event(frozen, H.hand_event("A", 3, 3, :withdrawn, %{amount_cents: 5}))

    assert {:error, :not_open} =
             H.apply_event(frozen, H.hand_event("A", 3, 3, :frozen, %{reason: :chargeback}))

    assert {:error, :not_frozen} =
             H.apply_event(s1, H.hand_event("A", 2, 2, :unfrozen, %{note: nil}))
  end

  test "T15 an unknown event type is reported by name" do
    alien = %{
      H.hand_event("A", 1, 1, :deposited, %{amount_cents: 5})
      | payload: %Ash.Union{type: :teleported, value: %{}}
    }

    assert {:error, {:unknown_event_type, :teleported}} = H.apply_event(H.initial("A"), alien)
  end

  test "T16 replay folds a tail and surfaces the first failure" do
    state = H.initial("A")
    assert {:ok, ^state} = H.replay(state, [])

    {:ok, s1} =
      H.apply_event(
        state,
        H.hand_event("A", 1, 1, :account_opened, %{owner: "Ada", opening_balance_cents: 500})
      )

    tail = [
      H.hand_event("A", 2, 2, :deposited, %{amount_cents: 100}),
      H.hand_event("A", 3, 3, :deposited, %{amount_cents: 200}),
      H.hand_event("A", 4, 4, :withdrawn, %{amount_cents: 300})
    ]

    assert {:ok, folded} = H.replay(s1, tail)
    assert folded.balance_cents == 500
    assert folded.version == 4
    assert folded.deposit_count == 2
    assert folded.withdrawal_count == 1

    failing =
      tail ++ [H.hand_event("A", 5, 5, :withdrawn, %{amount_cents: 10_000})]

    assert {:error, :insufficient_funds} = H.replay(s1, failing)
  end

  test "T17 replay rejects out of order input instead of sorting it" do
    events = [
      H.hand_event("A", 1, 1, :account_opened, %{owner: "Ada", opening_balance_cents: 100}),
      H.hand_event("A", 2, 3, :deposited, %{amount_cents: 10}),
      H.hand_event("A", 3, 2, :deposited, %{amount_cents: 10})
    ]

    assert {:error, {:out_of_order, 2}} = H.replay(H.initial("A"), events)

    duplicated = [
      H.hand_event("A", 1, 1, :account_opened, %{owner: "Ada", opening_balance_cents: 100}),
      H.hand_event("A", 2, 2, :deposited, %{amount_cents: 10}),
      H.hand_event("A", 3, 2, :deposited, %{amount_cents: 10})
    ]

    assert {:error, {:out_of_order, 2}} = H.replay(H.initial("A"), duplicated)
  end

  test "T18 the fold performs no storage access" do
    events = [
      H.hand_event("A", 1, 1, :account_opened, %{owner: "Ada", opening_balance_cents: 100}),
      H.hand_event("A", 2, 2, :deposited, %{amount_cents: 10})
    ]

    assert {:ok, _} = H.replay(H.initial("A"), events)
    assert {:ok, _} = H.apply_event(H.initial("A"), hd(events))

    assert H.events() == []
    assert H.rows() == []
    assert H.snapshots() == []
    assert H.checkpoint() == 0
  end

  # ==========================================================================
  # Commands
  # ==========================================================================

  test "T19 opening an account returns the documented command result" do
    assert {:ok, result} =
             H.open("A", "Ada", %{opening_balance_cents: 1000, recorded_at: H.t(1)})

    assert result.__struct__ == H.command_result()
    assert result.command == :open_account
    assert result.account_id == "A"
    assert length(result.appended) == 1

    [event] = result.appended
    assert event.sequence == 1
    assert event.version == 1
    assert event.account_id == "A"
    assert event.payload.type == :account_opened
    assert event.payload.value.owner == "Ada"
    assert event.recorded_at == H.t(1)

    assert result.state.__struct__ == H.account_state()
    assert result.state.balance_cents == 1000
    assert result.state.status == :open
    assert result.state.version == 1
    assert result.state.owner == "Ada"
  end

  test "T20 deposits and withdrawals advance the stream" do
    H.open!("A", "Ada", %{opening_balance_cents: 1000, recorded_at: H.t(1)})

    assert {:ok, deposited} = H.deposit("A", 250, %{recorded_at: H.t(2)})
    assert [%{sequence: 2, version: 2}] = deposited.appended
    assert deposited.state.balance_cents == 1250
    assert deposited.state.deposit_count == 1

    assert {:ok, withdrawn} = H.withdraw("A", 400, %{recorded_at: H.t(3)})
    assert [%{sequence: 3, version: 3}] = withdrawn.appended
    assert withdrawn.command == :withdraw
    assert withdrawn.state.balance_cents == 850
    assert withdrawn.state.withdrawal_count == 1
    assert withdrawn.state.deposit_count == 1
  end

  test "T21 a transfer appends two events with consecutive sequences" do
    H.open!("A", "Ada", %{opening_balance_cents: 1000, recorded_at: H.t(1)})
    H.open!("B", "Bo", %{opening_balance_cents: 0, recorded_at: H.t(2)})

    assert {:ok, result} = H.transfer("A", "B", 300, %{recorded_at: H.t(3)})
    assert result.command == :transfer
    assert result.account_id == "A"

    assert Enum.map(result.appended, &{&1.sequence, &1.account_id, &1.version, &1.payload.type}) ==
             [{3, "A", 2, :withdrawn}, {4, "B", 2, :deposited}]

    assert Enum.all?(result.appended, &(&1.recorded_at == H.t(3)))
    assert result.state.balance_cents == 700
    assert result.state.version == 2

    assert {:ok, destination} = H.current("B")
    assert destination.balance_cents == 300
    assert destination.deposit_count == 1
    assert destination.version == 2
  end

  test "T22 a rejected transfer leaves no trace" do
    H.open!("A", "Ada", %{opening_balance_cents: 100, recorded_at: H.t(1)})
    H.open!("B", "Bo", %{opening_balance_cents: 0, recorded_at: H.t(2)})

    events_before = H.events()
    rows_before = H.row_maps()
    checkpoint_before = H.checkpoint()
    snapshots_before = H.snapshots()

    error = H.error_of(H.transfer("A", "B", 500, %{recorded_at: H.t(3)}))
    assert %Ash.Error.Action.InvalidArgument{} = error
    assert error.field == :amount_cents
    assert error.message == "insufficient funds"

    assert H.events() == events_before
    assert H.row_maps() == rows_before
    assert H.checkpoint() == checkpoint_before
    assert H.snapshots() == snapshots_before
    assert {:ok, %{balance_cents: 100}} = H.current("A")
    assert {:ok, %{balance_cents: 0}} = H.current("B")
  end

  test "T23 every invariant violation reports the documented field and message" do
    H.open!("A", "Ada", %{opening_balance_cents: 1000, recorded_at: H.t(1)})
    H.open!("B", "Bo", %{opening_balance_cents: 0, recorded_at: H.t(2)})
    H.open!("F", "Fro", %{opening_balance_cents: 100, recorded_at: H.t(3)})
    H.freeze!("F", :fraud_review, %{recorded_at: H.t(4)})

    cases = [
      {fn -> H.deposit("A", 0) end, :amount_cents, "amount must be positive"},
      {fn -> H.withdraw("A", -1) end, :amount_cents, "amount must be positive"},
      {fn -> H.transfer("A", "B", 0) end, :amount_cents, "amount must be positive"},
      {fn -> H.open("C", "Cy", %{opening_balance_cents: -1}) end, :opening_balance_cents,
       "opening balance must not be negative"},
      {fn -> H.transfer("A", "A", 10) end, :to_account_id, "cannot transfer to the same account"},
      {fn -> H.open("A", "Other") end, :account_id, "account already exists"},
      {fn -> H.deposit("NOPE", 10) end, :account_id, "account does not exist"},
      {fn -> H.withdraw("NOPE", 10) end, :account_id, "account does not exist"},
      {fn -> H.transfer("NOPE", "B", 10) end, :from_account_id, "account does not exist"},
      {fn -> H.transfer("A", "NOPE", 10) end, :to_account_id, "account does not exist"},
      {fn -> H.deposit("F", 10) end, :account_id, "account is frozen"},
      {fn -> H.withdraw("F", 10) end, :account_id, "account is frozen"},
      {fn -> H.transfer("F", "B", 10) end, :from_account_id, "account is frozen"},
      {fn -> H.transfer("A", "F", 10) end, :to_account_id, "account is frozen"},
      {fn -> H.freeze("F", :chargeback) end, :account_id, "account is not open"},
      {fn -> H.unfreeze("A") end, :account_id, "account is not frozen"},
      {fn -> H.withdraw("A", 10_000) end, :amount_cents, "insufficient funds"}
    ]

    events_before = H.events()

    for {call, field, message} <- cases do
      error = H.error_of(call.())

      assert %Ash.Error.Action.InvalidArgument{} = error

      assert {error.field, error.message} == {field, message},
             "expected {#{inspect(field)}, #{inspect(message)}}, got #{inspect({error.field, error.message})}"
    end

    assert H.events() == events_before
  end

  test "T24 freezing blocks money movement until the account is unfrozen" do
    H.open!("A", "Ada", %{opening_balance_cents: 500, recorded_at: H.t(1)})
    H.freeze!("A", :court_order, %{recorded_at: H.t(2)})

    assert %{message: "account is frozen"} = H.error_of(H.deposit("A", 10))
    assert %{message: "account is frozen"} = H.error_of(H.withdraw("A", 10))

    assert {:ok, unfrozen} = H.unfreeze("A", %{note: "cleared", recorded_at: H.t(3)})
    assert unfrozen.state.status == :open
    assert [%{version: 3}] = unfrozen.appended
    assert hd(unfrozen.appended).payload.value.note == "cleared"

    assert {:ok, after_deposit} = H.deposit("A", 10, %{recorded_at: H.t(4)})
    assert after_deposit.state.balance_cents == 510
    assert after_deposit.state.status == :open
  end

  test "T25 an omitted recorded_at falls back to the current time" do
    before = DateTime.utc_now()
    {:ok, result} = H.open("A", "Ada", %{opening_balance_cents: 1})
    later = DateTime.utc_now()

    [event] = result.appended
    assert DateTime.compare(event.recorded_at, before) != :lt
    assert DateTime.compare(event.recorded_at, later) != :gt
  end

  test "T26 commands are generic actions returning the command result struct" do
    for name <- [:open_account, :deposit, :withdraw, :transfer, :freeze, :unfreeze] do
      action = Ash.Resource.Info.action(H.event(), name)
      assert action, "Vault.Ledger.Event is missing the #{name} action"
      assert action.type == :action, "#{name} must be a generic action"
      assert action.returns == Ash.Type.Struct, "#{name} must return a struct"

      assert action.constraints[:instance_of] == H.command_result(),
             "#{name} must be constrained to Vault.Ledger.CommandResult"
    end
  end

  # ==========================================================================
  # Snapshots
  # ==========================================================================

  test "T27 snapshot serialisation is exact and round trips" do
    assert H.interval() == 5

    state =
      H.mkstate(%{
        account_id: "A",
        owner: "Ada",
        balance_cents: 1250,
        status: :open,
        version: 2,
        deposit_count: 1,
        withdrawal_count: 0,
        last_event_type: :deposited,
        last_recorded_at: H.t(2)
      })

    assert H.dump(state) == %{
             "account_id" => "A",
             "owner" => "Ada",
             "balance_cents" => 1250,
             "status" => "open",
             "version" => 2,
             "deposit_count" => 1,
             "withdrawal_count" => 0,
             "last_event_type" => "deposited",
             "last_recorded_at" => "2026-03-01T10:00:02.000000Z"
           }

    assert H.restore(H.dump(state)) == state

    initial = H.initial("Z")

    assert H.dump(initial) == %{
             "account_id" => "Z",
             "owner" => nil,
             "balance_cents" => 0,
             "status" => "absent",
             "version" => 0,
             "deposit_count" => 0,
             "withdrawal_count" => 0,
             "last_event_type" => nil,
             "last_recorded_at" => nil
           }

    assert H.restore(H.dump(initial)) == initial
  end

  test "T28 the checksum covers exactly the documented fields" do
    state =
      H.mkstate(%{
        account_id: "A",
        owner: "Ada",
        balance_cents: 1250,
        status: :open,
        version: 2,
        deposit_count: 1,
        withdrawal_count: 0,
        last_event_type: :deposited,
        last_recorded_at: H.t(2)
      })

    expected = :sha256 |> :crypto.hash("A|2|1250|open|1|0") |> Base.encode16(case: :lower)
    assert H.checksum(state) == expected

    assert H.checksum(%{state | owner: "Zed"}) == expected
    assert H.checksum(%{state | last_recorded_at: nil}) == expected
    assert H.checksum(%{state | last_event_type: :withdrawn}) == expected

    assert H.checksum(%{state | balance_cents: 1251}) != expected
    assert H.checksum(%{state | version: 3}) != expected
    assert H.checksum(%{state | status: :frozen}) != expected
    assert H.checksum(%{state | deposit_count: 2}) != expected
    assert H.checksum(%{state | withdrawal_count: 1}) != expected
  end

  test "T29 commands snapshot every fifth version" do
    H.open!("A", "Ada", %{opening_balance_cents: 0, recorded_at: H.t(1)})
    for n <- 2..4, do: H.deposit!("A", 10, %{recorded_at: H.t(n)})

    assert H.snapshots() == []
    assert H.latest("A") == :none

    H.deposit!("A", 10, %{recorded_at: H.t(5)})

    assert [snapshot] = H.snapshots()
    assert snapshot.account_id == "A"
    assert snapshot.version == 5
    assert snapshot.sequence == 5

    assert {:ok, state_at_5} = H.state_at("A", {:version, 5})
    assert snapshot.state == H.dump(state_at_5)
    assert snapshot.checksum == H.expected_checksum(state_at_5)

    for n <- 6..10, do: H.deposit!("A", 10, %{recorded_at: H.t(n)})

    assert Enum.map(H.snapshots(), & &1.version) == [5, 10]
    assert {:ok, latest} = H.latest("A")
    assert latest.version == 10
    assert H.latest("UNKNOWN") == :none
  end

  test "T30 direct appends never create a snapshot" do
    H.append!(%{
      account_id: "D",
      version: 1,
      payload: H.payload_map(:account_opened, "Dee", 100),
      recorded_at: H.t(1)
    })

    for version <- 2..5 do
      H.append!(%{
        account_id: "D",
        version: version,
        payload: H.payload_map(:deposited, 10),
        recorded_at: H.t(version)
      })
    end

    assert length(H.events()) == 5
    assert H.snapshots() == []
    assert H.latest("D") == :none
  end

  test "T31 snapshot verification detects tampering" do
    H.open!("A", "Ada", %{opening_balance_cents: 0, recorded_at: H.t(1)})
    for n <- 2..5, do: H.deposit!("A", 10, %{recorded_at: H.t(n)})

    assert {:ok, snapshot} = H.latest("A")
    assert H.verify(snapshot) == :ok

    corrupted =
      Ash.Seed.update!(snapshot, %{state: Map.put(snapshot.state, "balance_cents", 999_999)})

    assert H.verify(corrupted) == {:error, :checksum_mismatch}

    assert {:ok, at_three} = H.state_at("A", {:version, 3})
    lying = %{at_three | version: 99}

    mismatched =
      Ash.Seed.seed!(H.snapshot(), %{
        account_id: "A",
        version: 3,
        sequence: 3,
        state: H.dump(lying),
        checksum: H.expected_checksum(lying)
      })

    assert H.verify(mismatched) == {:error, :version_mismatch}
  end

  test "T32 the current state is reconstructed from the newest valid snapshot" do
    H.open!("A", "Ada", %{opening_balance_cents: 1000, recorded_at: H.t(1)})
    H.deposit!("A", 200, %{recorded_at: H.t(2)})
    H.deposit!("A", 300, %{recorded_at: H.t(3)})
    H.deposit!("A", 400, %{recorded_at: H.t(4)})

    assert H.snapshots() == []

    assert {:ok, at_three} = H.state_at("A", {:version, 3})
    forged = %{at_three | balance_cents: at_three.balance_cents + 1000}

    Ash.Seed.seed!(H.snapshot(), %{
      account_id: "A",
      version: 3,
      sequence: 3,
      state: H.dump(forged),
      checksum: H.expected_checksum(forged)
    })

    assert {:ok, current} = H.current("A")
    assert current.balance_cents == 2900
    assert current.version == 4

    assert {:ok, truth} = H.fold_all("A")
    assert truth.balance_cents == 1900
    assert truth.version == 4
  end

  test "T33 a newer snapshot supersedes an older one" do
    H.open!("A", "Ada", %{opening_balance_cents: 1000, recorded_at: H.t(1)})
    H.deposit!("A", 200, %{recorded_at: H.t(2)})
    H.deposit!("A", 300, %{recorded_at: H.t(3)})
    H.deposit!("A", 400, %{recorded_at: H.t(4)})

    for {version, offset} <- [{3, 1000}, {4, 7}] do
      assert {:ok, state} = H.state_at("A", {:version, version})
      forged = %{state | balance_cents: state.balance_cents + offset}

      Ash.Seed.seed!(H.snapshot(), %{
        account_id: "A",
        version: version,
        sequence: version,
        state: H.dump(forged),
        checksum: H.expected_checksum(forged)
      })
    end

    assert {:ok, current} = H.current("A")
    assert current.balance_cents == 1907
    assert current.version == 4
  end

  test "T34 a corrupt snapshot is ignored rather than trusted" do
    H.open!("A", "Ada", %{opening_balance_cents: 1000, recorded_at: H.t(1)})
    H.deposit!("A", 200, %{recorded_at: H.t(2)})
    H.deposit!("A", 300, %{recorded_at: H.t(3)})
    H.deposit!("A", 400, %{recorded_at: H.t(4)})

    assert {:ok, at_three} = H.state_at("A", {:version, 3})
    forged = %{at_three | balance_cents: at_three.balance_cents + 1000}

    Ash.Seed.seed!(H.snapshot(), %{
      account_id: "A",
      version: 3,
      sequence: 3,
      state: H.dump(forged),
      checksum: "0000000000000000000000000000000000000000000000000000000000000000"
    })

    assert {:ok, current} = H.current("A")
    assert current.balance_cents == 1900
    assert H.current("A") == H.fold_all("A")
  end

  # ==========================================================================
  # Read model, checkpoint and rebuild
  # ==========================================================================

  test "T35 commands keep the read model up to date" do
    H.open!("A", "Ada", %{opening_balance_cents: 1000, recorded_at: H.t(1)})
    H.open!("B", "Bo", %{opening_balance_cents: 0, recorded_at: H.t(2)})
    H.deposit!("A", 250, %{recorded_at: H.t(3)})
    H.transfer!("A", "B", 300, %{recorded_at: H.t(4)})
    H.freeze!("B", :chargeback, %{recorded_at: H.t(5)})

    assert H.checkpoint() == 6
    assert Enum.map(H.rows(), & &1.account_id) == ["A", "B"]

    for account <- ["A", "B"] do
      assert {:ok, state} = H.fold_all(account)
      row = H.row(account)

      assert row.owner == state.owner
      assert row.balance_cents == state.balance_cents
      assert row.status == state.status
      assert row.version == state.version
      assert row.deposit_count == state.deposit_count
      assert row.withdrawal_count == state.withdrawal_count
      assert row.last_recorded_at == state.last_recorded_at

      assert row.last_event_sequence ==
               account |> H.events_for() |> List.last() |> Map.fetch!(:sequence)
    end

    assert H.row("A").balance_cents == 950
    assert H.row("B").balance_cents == 300
    assert H.row("B").status == :frozen
  end

  test "T36 direct appends only reach the read model through catch up" do
    H.open!("A", "Ada", %{opening_balance_cents: 1000, recorded_at: H.t(1)})
    H.deposit!("A", 100, %{recorded_at: H.t(2)})

    checkpoint_before = H.checkpoint()
    rows_before = H.row_maps()
    assert checkpoint_before == 2

    for {version, amount} <- [{3, 30}, {4, 40}] do
      H.append!(%{
        account_id: "A",
        version: version,
        payload: H.payload_map(:deposited, amount),
        recorded_at: H.t(version)
      })
    end

    assert H.checkpoint() == checkpoint_before
    assert H.row_maps() == rows_before

    assert {:ok, %{applied: 2, checkpoint: 4}} = H.catch_up()
    assert H.row("A").balance_cents == 1170
    assert H.row("A").version == 4
    assert H.row("A").deposit_count == 3
    assert H.row("A").last_event_sequence == 4
    assert H.checkpoint() == 4
  end

  test "T37 catch up is idempotent" do
    H.open!("A", "Ada", %{opening_balance_cents: 1000, recorded_at: H.t(1)})
    H.deposit!("A", 100, %{recorded_at: H.t(2)})

    H.append!(%{
      account_id: "A",
      version: 3,
      payload: H.payload_map(:deposited, 30),
      recorded_at: H.t(3)
    })

    assert {:ok, %{applied: 1, checkpoint: 3}} = H.catch_up()
    snapshot_of_rows = H.row_maps()

    assert {:ok, %{applied: 0, checkpoint: 3}} = H.catch_up()
    assert H.row_maps() == snapshot_of_rows

    assert {:ok, %{applied: 0, checkpoint: 3}} = H.catch_up()
    assert H.row_maps() == snapshot_of_rows
    assert H.checkpoint() == 3
  end

  test "T38 a full rebuild reproduces the incrementally maintained rows" do
    H.open!("A", "Ada", %{opening_balance_cents: 1000, recorded_at: H.t(1)})
    H.open!("B", "Bo", %{opening_balance_cents: 50, recorded_at: H.t(2)})
    H.deposit!("A", 250, %{recorded_at: H.t(3)})
    H.withdraw!("A", 100, %{recorded_at: H.t(4)})
    H.transfer!("A", "B", 300, %{recorded_at: H.t(5)})
    H.freeze!("A", :fraud_review, %{recorded_at: H.t(6)})
    H.unfreeze!("A", %{recorded_at: H.t(7)})

    incremental = H.row_maps()
    highest = H.events() |> List.last() |> Map.fetch!(:sequence)

    assert {:ok, %{rows: 2, checkpoint: ^highest}} = H.rebuild()
    assert H.row_maps() == incremental
    assert H.checkpoint() == highest
  end

  test "T39 a rebuild repairs a projection row edited behind its back" do
    H.open!("A", "Ada", %{opening_balance_cents: 1000, recorded_at: H.t(1)})
    H.deposit!("A", 250, %{recorded_at: H.t(2)})

    truth = H.row_map(H.row("A"))

    Ash.Seed.update!(H.row("A"), %{balance_cents: 42, version: 1, deposit_count: 99})
    assert H.row("A").balance_cents == 42

    assert {:ok, %{rows: 1}} = H.rebuild()
    assert H.row_map(H.row("A")) == truth
    assert H.row("A").balance_cents == 1250
    assert H.row("A").deposit_count == 1
  end

  test "T40 a rebuild recreates a deleted projection row" do
    H.open!("A", "Ada", %{opening_balance_cents: 1000, recorded_at: H.t(1)})
    H.open!("B", "Bo", %{opening_balance_cents: 25, recorded_at: H.t(2)})
    H.deposit!("A", 250, %{recorded_at: H.t(3)})

    truth = H.row_map(H.row("A"))
    Ash.destroy!(H.row("A"))
    assert Enum.map(H.rows(), & &1.account_id) == ["B"]

    assert {:ok, %{rows: 2, checkpoint: 3}} = H.rebuild()
    assert Enum.map(H.rows(), & &1.account_id) == ["A", "B"]
    assert H.row_map(H.row("A")) == truth
  end

  test "T41 rebuilding an empty log clears the read model" do
    Ash.Seed.seed!(H.projection(), %{
      account_id: "GHOST",
      owner: "nobody",
      balance_cents: 500,
      status: :open,
      version: 3,
      deposit_count: 1,
      withdrawal_count: 0,
      last_event_sequence: 3,
      last_recorded_at: H.t(1)
    })

    assert length(H.rows()) == 1
    assert H.events() == []

    assert {:ok, %{rows: 0, checkpoint: 0}} = H.rebuild()
    assert H.rows() == []
    assert H.checkpoint() == 0
  end

  test "T42 events appended during a rebuild belong to the next catch up" do
    H.open!("A", "Ada", %{opening_balance_cents: 1000, recorded_at: H.t(1)})
    H.open!("B", "Bo", %{opening_balance_cents: 0, recorded_at: H.t(2)})
    H.deposit!("A", 100, %{recorded_at: H.t(3)})

    assert H.checkpoint() == 3

    apply(H.hook(), :clear, [:after_load])

    apply(H.hook(), :set, [
      :after_load,
      fn ->
        H.append!(%{
          account_id: "B",
          version: 2,
          payload: H.payload_map(:deposited, 70),
          recorded_at: H.t(10)
        })

        H.append!(%{
          account_id: "A",
          version: 3,
          payload: H.payload_map(:deposited, 7),
          recorded_at: H.t(11)
        })
      end
    ])

    assert {:ok, %{rows: 2, checkpoint: 3}} = H.rebuild()
    assert apply(H.hook(), :count, [:after_load]) == 1
    apply(H.hook(), :clear, [:after_load])

    assert H.row("A").balance_cents == 1100
    assert H.row("B").balance_cents == 0
    assert H.checkpoint() == 3

    assert {:ok, %{applied: 2, checkpoint: 5}} = H.catch_up()
    assert H.row("A").balance_cents == 1107
    assert H.row("B").balance_cents == 70

    assert {:ok, %{applied: 0, checkpoint: 5}} = H.catch_up()
    assert H.row("A").balance_cents == 1107
    assert H.row("B").balance_cents == 70
  end

  test "T43 an unfoldable event halts the projection at the last good sequence" do
    H.open!("A", "Ada", %{opening_balance_cents: 1000, recorded_at: H.t(1)})
    H.deposit!("A", 100, %{recorded_at: H.t(2)})

    good_rows = H.row_maps()
    assert H.checkpoint() == 2

    H.append!(%{
      account_id: "GHOST",
      version: 1,
      payload: H.payload_map(:deposited, 5),
      recorded_at: H.t(3)
    })

    assert {:error, {:fold_failed, 3, :account_absent}} = H.catch_up()
    assert H.checkpoint() == 2
    assert H.row_maps() == good_rows
    assert H.row("GHOST") == nil
  end

  # ==========================================================================
  # Time travel and audit
  # ==========================================================================

  test "T44 time travel and the audit trail" do
    H.open!("A", "Ada", %{opening_balance_cents: 1000, recorded_at: H.t(1)})
    H.deposit!("A", 250, %{recorded_at: H.t(2)})
    H.withdraw!("A", 400, %{recorded_at: H.t(3)})
    H.freeze!("A", :court_order, %{recorded_at: H.t(4)})
    H.unfreeze!("A", %{recorded_at: H.t(5)})

    assert {:ok, zero} = H.state_at("A", {:version, 0})
    assert zero == H.initial("A")

    assert {:ok, two} = H.state_at("A", {:version, 2})
    assert {two.balance_cents, two.version, two.status} == {1250, 2, :open}

    assert {:ok, four} = H.state_at("A", {:version, 4})
    assert {four.balance_cents, four.status} == {850, :frozen}

    assert {:ok, beyond} = H.state_at("A", {:version, 99})
    assert {:ok, full} = H.fold_all("A")
    assert beyond == full

    assert {:ok, at_three} = H.state_at("A", {:timestamp, H.t(3)})
    assert {at_three.balance_cents, at_three.version} == {850, 3}

    assert {:ok, just_before} =
             H.state_at("A", {:timestamp, DateTime.add(H.t(3), -1, :microsecond)})

    assert just_before.version == 2

    assert {:ok, unknown} = H.state_at("UNKNOWN", {:version, 5})
    assert unknown == H.initial("UNKNOWN")

    assert H.state_at("A", {:version, -1}) == {:error, :invalid_point}
    assert H.state_at("A", {:bogus, 1}) == {:error, :invalid_point}
    assert H.state_at("A", :now) == {:error, :invalid_point}

    audit = H.audit("A")
    assert length(audit) == 5

    assert Enum.map(audit, &Map.keys(&1) |> Enum.sort()) ==
             List.duplicate(
               Enum.sort([
                 :sequence,
                 :version,
                 :type,
                 :balance_before,
                 :balance_after,
                 :delta_cents,
                 :status_before,
                 :status_after,
                 :recorded_at
               ]),
               5
             )

    assert Enum.map(audit, &{&1.version, &1.type, &1.delta_cents}) == [
             {1, :account_opened, 1000},
             {2, :deposited, 250},
             {3, :withdrawn, -400},
             {4, :frozen, 0},
             {5, :unfrozen, 0}
           ]

    assert Enum.map(audit, &{&1.balance_before, &1.balance_after}) == [
             {0, 1000},
             {1000, 1250},
             {1250, 850},
             {850, 850},
             {850, 850}
           ]

    assert Enum.map(audit, &{&1.status_before, &1.status_after}) == [
             {:absent, :open},
             {:open, :open},
             {:open, :open},
             {:open, :frozen},
             {:frozen, :open}
           ]

    assert Enum.map(audit, & &1.sequence) == [1, 2, 3, 4, 5]
    assert Enum.map(audit, & &1.recorded_at) == Enum.map(1..5, &H.t/1)

    assert H.audit("UNKNOWN") == []
  end
end

ExUnit.run()
"""


def _run(args, timeout=900):
    env = dict(os.environ)
    env.setdefault("MIX_ENV", "dev")
    env.setdefault("HEX_OFFLINE", "1")
    return subprocess.run(
        args,
        cwd=PROJECT_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


@pytest.fixture(scope="session")
def suite_results():
    """Compile the project, run the ExUnit contract suite, and parse its output."""
    compiled = _run(["mix", "compile"])
    assert compiled.returncode == 0, (
        "`mix compile` failed in "
        f"{PROJECT_DIR}:\nSTDOUT:\n{compiled.stdout}\nSTDERR:\n{compiled.stderr}"
    )

    with open(SUITE_PATH, "w", encoding="utf-8") as handle:
        handle.write(SUITE_SOURCE.lstrip("\n"))

    try:
        result = _run(["mix", "run", SUITE_PATH])
    finally:
        if os.path.exists(SUITE_PATH):
            os.remove(SUITE_PATH)

    parsed = {}
    for line in result.stdout.splitlines():
        if not line.startswith("@@HARBOR@@"):
            continue
        parts = line.split("@@")
        if len(parts) < 5:
            continue
        name, status, encoded = parts[2], parts[3], parts[4]
        words = name.split()
        if len(words) < 2:
            continue
        try:
            detail = base64.b64decode(encoded).decode("utf-8", errors="replace")
        except Exception:  # pragma: no cover - defensive
            detail = encoded
        parsed[words[1]] = (status, detail)

    tail = "\n".join((result.stdout + "\n" + result.stderr).splitlines()[-80:])
    return {"results": parsed, "tail": tail, "returncode": result.returncode}


def _assert_scenario(suite_results, scenario_id, description):
    results = suite_results["results"]
    assert scenario_id in results, (
        f"Scenario {scenario_id} ({description}) produced no result. The ExUnit suite "
        "did not run to completion. Last output:\n" + suite_results["tail"]
    )
    status, detail = results[scenario_id]
    assert status == "pass", (
        f"Scenario {scenario_id} ({description}) failed:\n{detail}"
    )


@pytest.mark.parametrize("scenario_id,description", SCENARIOS)
def test_scenario(suite_results, scenario_id, description):
    _assert_scenario(suite_results, scenario_id, description)
