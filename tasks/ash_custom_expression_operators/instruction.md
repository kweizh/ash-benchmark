# Extend the Ash expression language for SLA analytics

## Background

`/home/user/sla_lab` is an Elixir project that tracks courier shipments with **Ash Framework 3.31.0** (Elixir 1.18.4 / OTP 27.3.4). The domain `SlaLab.Ops` owns two resources backed by `Ash.DataLayer.Ets`:

- `SlaLab.Ops.Carrier` — `code` (string), `tier` (atom), `has_many :shipments`
- `SlaLab.Ops.Shipment` — `reference`, `origin_zone`, `destination_zone` (strings), `promised_hours`, `actual_hours` (integers, `actual_hours` may be `nil`), `priority` (atom), `belongs_to :carrier`

The operations team keeps re-writing the same two pieces of arithmetic in filters, calculations, aggregates, validations and policies. They now want those two pieces of arithmetic to become **first class parts of the Ash expression language**: callable by name inside any `expr(...)`, anywhere Ash evaluates expressions.

The environment is fully offline. Every dependency is already fetched, compiled and pinned in `mix.lock`; do not add, remove or upgrade dependencies.

## Requirements

### 1. Two reusable expression building blocks

After your change, `route_key(left, right)` and `ratio_bps(numerator, denominator)` must be callable **by name** inside any Ash expression in this application — query filters, action filters, expression calculations, aggregate filters, sorts, validations, policies and `Ash.Expr.eval/2` — without any per-call-site helper.

**`SlaLab.Expressions.RouteKey` — `route_key/2`**

- reports the name `:route_key` and the argument types `[[:string, :string]]`
- value: `nil` if either argument is `nil`; otherwise both arguments upper-cased and joined with a single `"|"`, with the lexicographically smaller upper-cased value first, so the result does not depend on argument order
- `route_key("ams", "jfk")` and `route_key("jfk", "ams")` are both `"AMS|JFK"`; `route_key("AMS", "ams")` is `"AMS|AMS"`

**`SlaLab.Expressions.RatioBps` — `ratio_bps/2`**

- reports the name `:ratio_bps` and the argument types `[[:integer, :integer]]`
- value: `nil` if either argument is `nil` **or** the denominator is `0`; otherwise `numerator * 10_000 / denominator` rounded to the nearest whole number with exact halves rounded **up** (towards positive infinity), and then clamped into the closed range `0..20_000`
- the result is always an Elixir **integer**, never a float
- `ratio_bps(1, 3) == 3333`, `ratio_bps(2, 3) == 6667`, `ratio_bps(1, 32) == 313`, `ratio_bps(3, 32) == 938`, `ratio_bps(3, 1) == 20_000`, `ratio_bps(-1, 4) == 0`, `ratio_bps(1, 0) == nil`
- denominators are never negative in the verified scenarios

Both modules must additionally satisfy this contract:

- an `expression/2` callback taking a data layer module and the argument list, returning `{:ok, expression}` for `Ash.DataLayer.Ets` **and** for `Ash.DataLayer.Simple`, and `:unknown` for every other data layer (e.g. `Ash.DataLayer.Mnesia`)
- the expression returned for `Ash.DataLayer.Ets` and the expression returned for `Ash.DataLayer.Simple` must evaluate to exactly the same values
- calling either name with arguments that cannot be cast to its declared argument types must surface as `Ash.Error.Query.NoSuchFunction`

### 2. Prove the building blocks work on the resources

Add to `SlaLab.Ops.Shipment` three public expression calculations:

- `:route_key` (`:string`) — the route key of `origin_zone` and `destination_zone`
- `:sla_ratio_bps` (`:integer`) — the ratio in basis points of `actual_hours` over `promised_hours`
- `:status_label` (`:string`) — `"pending"` when `actual_hours` is `nil`, `"breached"` when the SLA ratio is greater than `10_000`, otherwise `"met"`

`:sla_ratio_bps` and `:status_label` must be usable in `Ash.Query.filter/2`, and `:sla_ratio_bps` must be usable in `Ash.Query.sort/2`.

Add a read action `:on_route` to `SlaLab.Ops.Shipment` with a required string argument `:route` that returns exactly the shipments whose route key equals that argument, and expose it on the `SlaLab.Ops` domain as `shipments_on_route`, taking the route as its single positional argument.

Add an update action `:record_delivery` to `SlaLab.Ops.Shipment` that takes an integer input under the key `actual_hours`, writes it to the `actual_hours` attribute, and runs fully atomically (its `require_atomic?` must be `true`). The action must be rejected when the ratio in basis points of the **new** `actual_hours` over the record's `promised_hours` is greater than `15_000`. That check must be implemented by a validation module `SlaLab.Ops.Validations.RatioWithin` that is placed on the action with the option `max_bps: 15_000`, and it must hold for a single update as well as for `Ash.bulk_update/4` with `strategy: [:atomic]`. A rejected update must leave the record untouched and produce an `Ash.Error.Invalid` wrapping an `Ash.Error.Changes.InvalidAttribute` whose `field` is `:actual_hours` and whose `message` is exactly `delivery ratio exceeds the allowed maximum`.

Add to `SlaLab.Ops.Carrier`:

- an aggregate `:delivered_count` — how many of the carrier's shipments have a non-`nil` `actual_hours`
- an aggregate `:breach_count` — how many of the carrier's shipments have an SLA ratio in basis points greater than `10_000`
- a public expression calculation `:breach_rate_bps` (`:integer`) — the ratio in basis points of `:breach_count` over `:delivered_count`, which is therefore `nil` for a carrier with no delivered shipments

Both building blocks must also work when applied directly to aggregates inside `Ash.Query.filter/2` and inside `exists/2`.

Add policies to `SlaLab.Ops.Shipment` so that reads are authorised only when the actor's `:home_route` equals the shipment's route key, an actor whose `:role` is `:admin` may read every shipment regardless of its route, and a `nil` actor is refused with `Ash.Error.Forbidden`. All other actions stay unrestricted.

### 3. A custom query function

`SlaLab.Expressions.PenaltyPoints` must be an Ash query function module named `:penalty_points` that is constructed programmatically with `Ash.Query.Function.new/2` and used as a node inside expressions (query filters and `Ash.Expr.eval/2` with a `record:` binding).

- `args/0` returns `[[:integer, :integer]]`, `returns/0` returns `[:integer]`, `name/0` returns `:penalty_points`, `predicate?/0` returns `false`
- it must never be evaluated when any argument is `nil`; a `nil` argument yields a `nil` value
- `evaluate/1`, for a function whose `arguments` are `[late_hours, weight]`:
  - both integers and `weight >= 0`: `{:known, 0}` when `late_hours <= 0`; `{:known, late_hours * weight}` when `late_hours` is between `1` and `24`; `{:known, 24 * weight + (late_hours - 24) * weight * 2}` when `late_hours > 24`
  - both integers and `weight < 0`: `{:error, "penalty weight must not be negative"}`
  - any argument that is not an integer: `:unknown`

## Implementation Hints

- Project path: `/home/user/sla_lab`
- The project must compile cleanly with `mix compile` in the `dev` environment, and verification runs Elixir scripts with `mix run` from the project root in the `dev` environment.
- Verification seeds its fixtures by calling `SlaLab.Ops.Seed.seed!/0`; `lib/sla_lab/ops/seed.ex` must keep working exactly as shipped — do not modify it.
- Keep both resources on `Ash.DataLayer.Ets` with `private? true`, keep every existing attribute, relationship and action, and keep the existing `:create`, `:read` and `:destroy` action behaviour intact.
- Module names, expression names, calculation/aggregate/action/argument names, option names and message strings above are exact and are asserted verbatim.
- Everything runs locally and offline; no network access, no new dependencies, no database server.

