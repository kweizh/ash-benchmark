# Event-Sourced Ledger with Rebuildable Projections (Ash Framework v3)

## Background

A payments team needs an auditable account ledger in which the **event log is the only source of truth**. Balances, statuses and counters are never stored authoritatively: they are *derived* by folding an append-only event stream. Read models are caches that can be thrown away and rebuilt at any time, and snapshots exist purely to make that fold cheap.

You must build this write model, fold, snapshot layer and projection layer on top of **Ash Framework v3.31** using the in-memory ETS data layer. The project already exists, compiles, and has `ash 3.31` fetched and compiled. **There is no network access — do not add dependencies.**

## Requirements

### 1. Append-only event store

`Vault.Ledger.Event` is the log. Every event belongs to one aggregate (an account, identified by a plain string `account_id`) and carries:

| field | type | notes |
| --- | --- | --- |
| `id` | uuid primary key | |
| `sequence` | integer, required | **global** position in the log |
| `account_id` | string, required | aggregate identifier |
| `version` | integer, required | position **within** that aggregate's stream |
| `payload` | `Vault.Ledger.Payload`, required | the typed event body (see §2) |
| `recorded_at` | utc datetime with microseconds, required | supplied by the caller |

Contracts:

* `sequence` values across the whole log are exactly `1, 2, 3, …, n` with no gaps and no duplicates, assigned in append order. `sequence` is **derived by the store**: it is not part of the input of the append action, and passing it must be rejected by Ash's "no such input" error.
* `version` values within one `account_id` are exactly `1, 2, 3, …, k` with no gaps.
* Two identities must be declared and enforced (both must work on the ETS data layer): one over `[:account_id, :version]` and one over `[:sequence]`.
* Appending an event whose `version` is **already present** for that `account_id` must fail with `%Ash.Error.Changes.InvalidChanges{}` whose `fields` is `[:account_id, :version]` and whose `message` is `"has already been taken"`.
* Appending an event whose `version` is **less than 1** or **more than one greater** than that stream's current highest version must fail with `%Ash.Error.Changes.InvalidAttribute{}` where `field` is `:version`, `message` is exactly `"version must be exactly one greater than the current stream version"`, and `vars[:expected]` is the integer version that would have been accepted.
* A rejected append must leave the log completely untouched: no row is written and no global `sequence` value is consumed (the next successful append gets the next contiguous number).
* The log is immutable: the resource must declare **no update action and no destroy action of any kind**, and attempting `Ash.destroy/1` or `Ash.update/2` on a stored event must fail rather than mutate it.

### 2. Typed payloads

`Vault.Ledger.Payload` is an `Ash.Type.NewType` whose subtype is Ash's union type. It has exactly five tagged members, each backed by its own embedded resource and each discriminated by a string field named `type` whose value is the member name:

| member atom | embedded module | fields |
| --- | --- | --- |
| `:account_opened` | `Vault.Ledger.Payloads.AccountOpened` | `owner` (string, required, at least 1 character), `opening_balance_cents` (integer, required, minimum 0) |
| `:deposited` | `Vault.Ledger.Payloads.Deposited` | `amount_cents` (integer, required, minimum 1) |
| `:withdrawn` | `Vault.Ledger.Payloads.Withdrawn` | `amount_cents` (integer, required, minimum 1) |
| `:frozen` | `Vault.Ledger.Payloads.Frozen` | `reason` (atom, required, one of `:fraud_review`, `:chargeback`, `:court_order`) |
| `:unfrozen` | `Vault.Ledger.Payloads.Unfrozen` | `note` (string, optional, at most 120 characters) |

A payload is supplied to the append action as a plain string-keyed map such as `%{"type" => "deposited", "amount_cents" => 500}` and, once stored, is read back as an `%Ash.Union{}` whose `type` is the member atom and whose `value` is the corresponding embedded struct. A map whose `type` matches no member must be rejected on the `:payload` field. Each member's own field constraints must be enforced.

### 3. The fold (pure, side-effect free)

`Vault.Ledger.AccountState` is a struct with exactly these keys and defaults:

```
account_id: nil, owner: nil, balance_cents: 0, status: :absent, version: 0,
deposit_count: 0, withdrawal_count: 0, last_event_type: nil, last_recorded_at: nil
```

`Vault.Ledger.Fold` exposes:

* `initial/1` — takes an `account_id` and returns the struct above with `account_id` set.
* `apply_event/2` — takes an `%AccountState{}` and an `%Event{}` and returns `{:ok, %AccountState{}}` or `{:error, reason}`. It must not read or write any storage.
* `replay/2` — takes an `%AccountState{}` and a list of `%Event{}` and returns `{:ok, %AccountState{}}` or `{:error, reason}`. It must not read or write any storage.

`apply_event/2` rejects in this exact precedence, before any business rule is considered:

1. the event's `account_id` differs from the state's (and the state's is not `nil`) → `{:error, {:account_mismatch, state_account_id, event_account_id}}`
2. the event's `version` is not exactly `state.version + 1` → `{:error, {:version_gap, expected_version, actual_version}}`
3. the payload's union member is none of the five → `{:error, {:unknown_event_type, member_atom}}`

The business rules, and the resulting state transitions, are:

| member | precondition | on success |
| --- | --- | --- |
| `:account_opened` | `status` is `:absent`, else `{:error, :already_open}` | `owner` set, `balance_cents` set to `opening_balance_cents`, `status` becomes `:open` |
| `:deposited` | `status` is `:open`; `{:error, :account_absent}` when `:absent`, `{:error, :account_frozen}` when `:frozen` | `balance_cents` increased, `deposit_count` incremented |
| `:withdrawn` | `status` is `:open` (same two errors as above) and the resulting balance is not negative, else `{:error, :insufficient_funds}` | `balance_cents` decreased, `withdrawal_count` incremented |
| `:frozen` | `status` is `:open`, else `{:error, :not_open}` | `status` becomes `:frozen` |
| `:unfrozen` | `status` is `:frozen`, else `{:error, :not_frozen}` | `status` becomes `:open` |

On every success, `version` becomes the event's `version`, `last_event_type` becomes the member atom, and `last_recorded_at` becomes the event's `recorded_at`.

`replay/2` returns the starting state unchanged for an empty list, stops at the first failure and returns that failure verbatim, and **rejects rather than repairs** unsorted input: if the list is not strictly increasing by `sequence`, it returns `{:error, {:out_of_order, index}}` where `index` is the zero-based position of the first element whose `sequence` is not strictly greater than its predecessor's. This check happens before any event is applied.

### 4. Commands

Command handling is exposed as **generic actions on `Vault.Ledger.Event`**, each returning a `Vault.Ledger.CommandResult` struct with exactly the keys `command`, `account_id`, `appended`, `state`:

* `command` — the action name atom;
* `account_id` — the primary account of the command (for a transfer this is the *source* account);
* `appended` — the list of `%Event{}` records this command wrote, ordered by ascending `sequence`;
* `state` — the `%AccountState{}` of `account_id` after the command.

The actions, their arguments and the events they append:

| action | arguments | appends |
| --- | --- | --- |
| `:open_account` | `account_id` (string, required), `owner` (string, required), `opening_balance_cents` (integer, default `0`), `recorded_at` (utc datetime usec, optional) | one `account_opened` |
| `:deposit` | `account_id`, `amount_cents` (integer, required), `recorded_at` | one `deposited` |
| `:withdraw` | `account_id`, `amount_cents`, `recorded_at` | one `withdrawn` |
| `:transfer` | `from_account_id`, `to_account_id`, `amount_cents`, `recorded_at` | one `withdrawn` on the source **and** one `deposited` on the destination, in that order, with consecutive global sequences |
| `:freeze` | `account_id`, `reason` (atom, one of the three allowed reasons, required), `recorded_at` | one `frozen` |
| `:unfreeze` | `account_id`, `note` (string, optional), `recorded_at` | one `unfrozen` |

When `recorded_at` is not supplied it defaults to the current UTC time; when supplied, every event appended by that call carries it verbatim.

A command that violates an invariant must return an error and append **zero** events, consume **zero** sequence numbers, and leave every snapshot, projection row and checkpoint unchanged. The error is always `Ash.Error.Invalid` wrapping a single `%Ash.Error.Action.InvalidArgument{}` with the `field` and verbatim `message` given below; when several apply, the first matching row of this table wins:

| order | condition | field | message |
| --- | --- | --- | --- |
| 1 | `amount_cents` is not positive (`:deposit`, `:withdraw`, `:transfer`) | `:amount_cents` | `amount must be positive` |
| 2 | `opening_balance_cents` is negative (`:open_account`) | `:opening_balance_cents` | `opening balance must not be negative` |
| 3 | transfer source and destination are the same | `:to_account_id` | `cannot transfer to the same account` |
| 4 | `:open_account` for an account that already has events | `:account_id` | `account already exists` |
| 5 | the account has no events (any command other than `:open_account`) | `:account_id` (`:from_account_id` / `:to_account_id` for a transfer, source checked first) | `account does not exist` |
| 6 | account is frozen (`:deposit`, `:withdraw`, `:transfer`) | `:account_id` (`:from_account_id` / `:to_account_id` for a transfer, source checked first) | `account is frozen` |
| 7 | `:freeze` on an account that is not open | `:account_id` | `account is not open` |
| 8 | `:unfreeze` on an account that is not frozen | `:account_id` | `account is not frozen` |
| 9 | withdrawal or transfer larger than the balance | `:amount_cents` | `insufficient funds` |

### 5. Snapshots

`Vault.Ledger.Snapshot` stores `account_id` (string, required), `version` (integer, required), `sequence` (integer, required), `state` (map, required) and `checksum` (string, required), plus a uuid primary key, and declares an identity over `[:account_id, :version]`.

`Vault.Ledger.Snapshots` exposes:

* `interval/0` → `5`.
* `dump/1` — turns an `%AccountState{}` into the map stored in `state`, with **string keys** `"account_id"`, `"owner"`, `"balance_cents"`, `"status"`, `"version"`, `"deposit_count"`, `"withdrawal_count"`, `"last_event_type"`, `"last_recorded_at"`. `status` and `last_event_type` are stored as strings (`nil` stays `nil`) and `last_recorded_at` as an ISO-8601 string (`nil` stays `nil`).
* `restore/1` — the exact inverse of `dump/1`.
* `checksum/1` — takes an `%AccountState{}` and returns the lowercase hex SHA-256 digest of the string formed by joining, with `"|"`, in this order: `account_id`, `version`, `balance_cents`, `status` (as a string), `deposit_count`, `withdrawal_count`. No other field participates.
* `latest/1` — takes an `account_id` and returns `{:ok, %Snapshot{}}` for the **highest** stored `version`, or `:none`.
* `verify/1` — takes a `%Snapshot{}` and returns `:ok`, `{:error, :checksum_mismatch}` when `checksum/1` of the restored state does not equal the stored `checksum`, or `{:error, :version_mismatch}` when the restored state's `version` differs from the snapshot's `version`. The checksum is checked first.

Snapshots are written **by the command layer only**: after any command succeeds, every account whose stream that command extended must have a stored snapshot for every version `v ≤ its current version` where `rem(v, 5) == 0`, with the correct `sequence`, `state` and `checksum`. Appending directly through the event resource's append action must **not** create a snapshot.

### 6. Aggregate reconstruction

`Vault.Ledger.Aggregate` exposes two functions, both taking an `account_id` and returning `{:ok, %AccountState{}}` or the fold's error:

* `fold_all/1` — folds the account's entire stream from the initial state, ignoring snapshots entirely.
* `current/1` — must be accelerated by snapshots: it starts from the highest-version snapshot that passes `verify/1` and folds only the events after it. A snapshot that fails verification must be ignored (and any earlier valid one used instead, or a full fold if none is valid); `current/1` must never fail because a snapshot is corrupt.

### 7. Read model, checkpoint and rebuild

`Vault.Ledger.AccountProjection` is the read model, keyed by `account_id` (a string primary key), with required fields `owner` (string), `balance_cents` (integer), `status` (atom, one of `:open`/`:frozen`), `version` (integer), `deposit_count` (integer), `withdrawal_count` (integer), `last_event_sequence` (integer, the global sequence of the newest event applied to that account) and `last_recorded_at` (utc datetime usec).

`Vault.Ledger.Checkpoint` records how far the read model has consumed the log: `name` (string primary key) and `sequence` (integer). The projection's checkpoint row is named `"account_projection"`.

`Vault.Ledger.Projector` exposes:

* `checkpoint/0` → the stored sequence, or `0` when the row is absent.
* `catch_up/0` → `{:ok, %{applied: n, checkpoint: seq}}` where `n` is the number of events consumed by this call. It resumes strictly after the stored checkpoint, in ascending `sequence` order, updating or creating projection rows and advancing the checkpoint. Running it twice in a row must consume nothing the second time and change nothing.
* `rebuild_all/0` → `{:ok, %{rows: n, checkpoint: seq}}`. It discards **all** projection rows and rebuilds them from the log alone, in ascending `sequence` order. `rows` is the number of projection rows that exist afterwards, and `checkpoint` is the highest `sequence` among the events this pass actually folded (`0` for an empty log) — which is also what the checkpoint row must be left at.
* `state_at/2` → `{:ok, %AccountState{}}` for a point in time expressed as `{:version, n}` (fold events with `version ≤ n`; `n = 0` yields the initial state; `n` beyond the tail yields the full fold) or `{:timestamp, %DateTime{}}` (fold events with `recorded_at ≤ the given time`). Any other point, or a negative version, yields `{:error, :invalid_point}`.
* `audit/1` → the account's per-event diff list, ascending by `version`, each entry a map with exactly the keys `:sequence`, `:version`, `:type` (the union member atom), `:balance_before`, `:balance_after`, `:delta_cents` (after minus before), `:status_before`, `:status_after` and `:recorded_at`. An account with no events yields `[]`.

Whenever `catch_up/0`, `rebuild_all/0`, `state_at/2` or `audit/1` hits an event the fold rejects, it must stop before applying it and return `{:error, {:fold_failed, sequence, reason}}`, where `reason` is the fold's own error term and `sequence` is that event's global sequence; anything already applied stays applied and the checkpoint is left at the last successfully applied sequence.

Every successful command must leave the read model fully up to date (checkpoint equal to the log's highest sequence, every projection row equal to the folded state). Events appended directly through the event resource's append action must **not** update the read model — only `catch_up/0` or `rebuild_all/0` may.

### 8. Rebuild must be a real rebuild

The read model must be reconstructible from the log alone: if a projection row is edited behind the projector's back, or deleted outright, `rebuild_all/0` must restore exactly the folded values.

So that the verifier can drive a deterministic interleaving, `rebuild_all/0` must call `Vault.Ledger.Hook.run(:after_load)` **exactly once per invocation**, after it has read the set of events it is going to fold and before it deletes or writes any projection row. (`Vault.Ledger.Hook` already exists in the project; do not change it.) Events appended by that callback therefore belong to the *next* catch-up, not to this rebuild, and must be applied exactly once when `catch_up/0` next runs.

## Implementation Hints

* Project path: `/home/user/vault`. OTP application: `:vault`. Ash domain module: `Vault.Ledger`, already listed in `config/config.exs`; you must create it.
* All four resources (`Vault.Ledger.Event`, `Vault.Ledger.Snapshot`, `Vault.Ledger.AccountProjection`, `Vault.Ledger.Checkpoint`) must belong to that domain, must use Ash's built-in in-memory ETS data layer configured with **private** tables (so each process owns isolated storage — the verifier depends on this), and must each expose a primary read action.
* The event resource's create action that appends one event must be named `:append` and must accept `account_id`, `version`, `payload` and `recorded_at`.
* The domain must expose this code interface, with these exact names and positional arguments: `open_account/2..4` (`account_id`, `owner`), `deposit/2..4` (`account_id`, `amount_cents`), `withdraw/2..4` (`account_id`, `amount_cents`), `transfer/3..5` (`from_account_id`, `to_account_id`, `amount_cents`), `freeze_account/2..4` (`account_id`, `reason`) for the `:freeze` action, `unfreeze_account/1..3` (`account_id`) for the `:unfreeze` action, `append_event/1..2` for the `:append` action, and `list_events/0..2` for the event read action. Remaining arguments (`opening_balance_cents`, `note`, `recorded_at`) are passed in the params map. Bang variants must exist as usual.
* Everything the verifier calls is called as a plain Elixir function or through that code interface; there is no HTTP surface and no test file layout to honour. The verifier compiles the project with `mix compile` and then runs an ExUnit suite with `mix run <script>` from the project root in `MIX_ENV=dev`, so every module above must exist with exactly the stated name and arity.
* The verifier reads and writes the ETS-backed resources directly (including seeding forged snapshot and projection rows), so resource, attribute and action names must match exactly.
* No new dependencies: the container is offline and `mix.lock` is committed.

