# Schema-per-tenant billing on PostgreSQL with Ash

## Background

`/home/user/billing` is an Elixir/Ash project (OTP application `:billing`) that has to become the metering and
billing backend of a SaaS product. Every customer organisation gets **its own PostgreSQL schema**: per-customer
rows must physically live in that schema and never in a shared table. Every figure the product reports
(rollups, ratios, overage, fuzzy search) has to be produced by PostgreSQL itself, and every money-moving
operation has to be genuinely transactional and race-free.

PostgreSQL 16 runs inside this container. `pg-start` starts it and waits until it accepts connections; it is
idempotent and safe to run repeatedly. Connection settings for `Billing.Repo` are already in
`config/config.exs` (database `billing_dev`, host `127.0.0.1`, port `5432`, user `postgres`) — do not change
them. There is no network access; all dependencies are already vendored and compiled.

The project already ships `Billing.Repo` (with `min_pg_version/0`), `Billing.Application`, `Billing.Trace` and
an empty `Billing.Metering` domain. Everything else is yours to write.

## Requirements

### 1. Global data (lives in the `public` schema, readable with no tenant)

`Billing.Metering.Organisation` — table `organisations`, the tenant registry.

| attribute | type | notes |
| --- | --- | --- |
| `id` | uuid | primary key |
| `slug` | string | required, unique across the whole table |
| `name` | string | required |
| `plan_code` | string | required |
| `active` | boolean | required, defaults to `true` |

Actions: a primary read; a create named `:register` accepting `slug`, `name`, `plan_code`.

`Billing.Metering.PlanRate` — table `plan_rates`.

| attribute | type | notes |
| --- | --- | --- |
| `id` | uuid | primary key |
| `plan_code` | string | required, unique |
| `unit_cents` | integer | required |
| `included_units` | integer | required |

Actions: a primary read; a create named `:create` accepting `plan_code`, `unit_cents`, `included_units`.

A PostgreSQL function must exist in the database after migrating:

```
billing_overage_cents(quantity bigint, included bigint, unit_cents bigint) RETURNS bigint
  = GREATEST(COALESCE(quantity,0) - COALESCE(included,0), 0) * COALESCE(unit_cents,0)
```

It must be created by a migration (so `select count(*) from pg_proc where proname = 'billing_overage_cents'`
returns `1` on a freshly migrated database).

### 2. Tenant data (one PostgreSQL schema per organisation)

The schema backing the organisation whose slug is `S` is named `tenant_<S>`. Provide
`Billing.Tenancy.schema_name/1` (slug → schema name) and `Billing.Tenancy.slug_from_schema/1` (the inverse).
An `%Organisation{}` struct must also be usable directly wherever a tenant is expected, resolving to the same
schema name.

All of the following resources are tenant-scoped; a read, count, aggregate or write against any of them
without a tenant must fail with `Ash.Error.Invalid` containing an
`%Ash.Error.Invalid.TenantRequired{resource: <the resource>}`.

`Billing.Metering.Subscription` — table `subscriptions`

| attribute | type | notes |
| --- | --- | --- |
| `id` | uuid | primary key |
| `code` | string | required, unique **within a tenant** (the same code must be creatable in another tenant) |
| `plan_code` | string | required |
| `monthly_cents` | integer | required |
| `balance_cents` | integer | required, defaults to `0` |
| `status` | atom | required, one of `:active`, `:paused`, `:cancelled`, defaults to `:active` |
| `started_on` | date | required |

Relationships: belongs to one `PlanRate` through a writable `plan_rate_id` (a *global* resource — the emitted
SQL joins `"public"."plan_rates"`); has many `UsageRecord`; has many `Invoice`.

Actions: a primary read; a create named `:open` accepting `code`, `plan_code`, `monthly_cents`,
`balance_cents`, `started_on`, `plan_rate_id`; a read named `:search` taking a required string argument
`pattern`; a read named `:fuzzy` taking a required string argument `term` and a required float argument
`threshold`; a generic action named `:spend` (see §4).

`Billing.Metering.UsageRecord` — table `usage_records`

| attribute | type | notes |
| --- | --- | --- |
| `id` | uuid | primary key |
| `metric` | string | required |
| `quantity` | integer | required |
| `unit_price_cents` | integer | required |
| `recorded_at` | utc_datetime | required |
| `invoiced` | boolean | required, defaults to `false` |

Belongs to one `Subscription` through a required, writable `subscription_id`. Actions: a primary read; a
create named `:record` accepting `metric`, `quantity`, `unit_price_cents`, `recorded_at`, `subscription_id`.

`Billing.Metering.Invoice` — table `invoices`

| attribute | type | notes |
| --- | --- | --- |
| `id` | uuid | primary key |
| `number` | string | required, unique within a tenant |
| `status` | atom | required, one of `:draft`, `:issued`, `:void`, defaults to `:draft` |
| `total_cents` | integer | required, defaults to `0` |
| `issued_on` | date | nullable |

Belongs to one `Subscription` through a required, writable `subscription_id`; has many `InvoiceLine`; has a
many-to-many `tags` relationship to `Tag` through `InvoiceTag`. Actions: a primary read; a create named
`:draft` accepting `number`, `total_cents`, `subscription_id`; an update named `:issue` (see §4); a read named
`:numbered` taking a required string argument `pattern`; a generic action named `:close_period` (see §4).

`Billing.Metering.InvoiceLine` — table `invoice_lines`

| attribute | type | notes |
| --- | --- | --- |
| `id` | uuid | primary key |
| `description` | string | required |
| `quantity` | integer | required |
| `unit_cents` | integer | required |
| `amount_cents` | integer | required |

Belongs to one `Invoice` through a required, writable `invoice_id`. Actions: a primary read; a create named
`:create` accepting `description`, `quantity`, `unit_cents`, `amount_cents`, `invoice_id`.

`Billing.Metering.Tag` — table `tags`: `id` (uuid pk) and a required `name` that is unique within a tenant;
many-to-many `invoices` to `Invoice` through `InvoiceTag`. Actions: a primary read; a create named `:create`
accepting `name`.

`Billing.Metering.InvoiceTag` — table `invoice_tags`: the join between `Invoice` and `Tag`, with writable
`invoice_id` and `tag_id`. Actions: a primary read; a create named `:create` accepting both ids.

### 3. Provisioning, migrations and isolation

* Creating an `Organisation` must, at runtime, provision `tenant_<slug>` and create **every** tenant table in
  it, ready for immediate use.
* `Billing.Repo.all_tenants/0` must return exactly one schema name per row of `organisations`.
* `Billing.Repo.installed_extensions/0` must return a list containing `"ash-functions"` and `"pg_trgm"`.
* Migrations must be committed in the repository: public ones under `priv/repo/migrations`, tenant ones under
  `priv/repo/tenant_migrations`. The public migrations must create `organisations` and `plan_rates` and must
  **not** create any of the six tenant tables in `public`. Running the tenant migration path against an
  arbitrary empty schema (with `Ecto.Migrator`, `prefix:` that schema) must create all six tenant tables there.
* Tenant tables must carry no tenant discriminator: no column of `tenant_<slug>.subscriptions` may contain the
  substring `tenant` or `organisation`.
* Setting the tenant must scope reads, aggregates and relationship loads, and the SQL emitted for a tenant
  must be schema-qualified to that tenant's schema and mention no other tenant's schema.

### 4. Transactional behaviour

`:spend` — generic action on `Subscription` returning an `:integer`. Arguments: `subscription_id` (uuid,
required) and `amount_cents` (integer, required). It runs in a database transaction, and the statement that
reads the subscription inside it must acquire a row-level write lock (the emitted SQL contains `FOR UPDATE`).
If the stored balance is smaller than `amount_cents` it must fail with `Ash.Error.Invalid` containing
`%Ash.Error.Changes.InvalidArgument{field: :amount_cents}` whose `message` is exactly `insufficient balance`,
leaving the balance untouched. Otherwise it decrements `balance_cents` by `amount_cents` and returns
`{:ok, new_balance}`. Concurrent callers must never overspend: with a balance of `B`, `N` simultaneous calls
each spending `A` must produce exactly `min(N, div(B, A))` successes and a final balance of
`B - A * min(N, div(B, A))`.

`:close_period` — generic action on `Invoice` returning the created `Invoice` struct. Arguments:
`subscription_id` (uuid, required), `number` (string, required), `cap_cents` (integer, required). It must be
declared transactional and declare that it touches `Invoice`, `InvoiceLine` and `UsageRecord`. In one
transaction it creates a `:draft` invoice for that subscription whose `total_cents` is the sum of
`quantity * unit_price_cents` over every not-yet-invoiced usage record of that subscription, creates one
`InvoiceLine` per such usage record (`description` = the usage record's `metric`, `quantity` = its `quantity`,
`unit_cents` = its `unit_price_cents`, `amount_cents` = the product), and marks those usage records
`invoiced`. If the resulting total is greater than `cap_cents` the action must fail with `Ash.Error.Invalid`
containing `%Ash.Error.Changes.InvalidArgument{field: :cap_cents}` whose `message` is exactly
`period total exceeds cap`, and **nothing at all** may remain persisted: no invoice, no invoice lines, and
every usage record still `invoiced == false`.

`:issue` — update on `Invoice`, accepting no attributes. It sets `status` to `:issued` and `issued_on` to
today's date. It must append these entries to `Billing.Trace` (which is already provided, do not change its
API), in this exact order:

1. `"issue:before_action"` — before the row is written;
2. `"issue:after_action"` — after the row is written but still inside the transaction; if the invoice's
   `total_cents` is `0` the action must fail at this point with `Ash.Error.Invalid` containing an
   `%Ash.Error.Changes.InvalidChanges{}` whose `message` is exactly `cannot issue an empty invoice`, and the
   stored invoice must remain `status: :draft` with `issued_on: nil`;
3. `"issue:after_transaction:ok"` when the transaction committed, or `"issue:after_transaction:error"` when it
   was rolled back — this entry must be produced on **both** paths.

### 5. Derived values, all computed by PostgreSQL

**SQL-visibility contract.** The verifier attaches to `Billing.Repo`'s Ecto query telemetry and inspects every
statement the application issues. Loading any set of the fields below over *all* records of a tenant must
issue **exactly one** SQL statement, and that statement must textually contain the PostgreSQL construct named
for each field. Anything computed in Elixir after the rows come back will fail these checks.

On `UsageRecord`:

| field | type | value | SQL must contain |
| --- | --- | --- | --- |
| `line_total_cents` | integer | `quantity * unit_price_cents` | — |
| `recorded_month` | string | `recorded_at` formatted as `YYYY-MM` | `to_char(` |
| `metric_label` | string | `metric` upper-cased | `upper(` |
| `retention_until` | utc_datetime | `recorded_at` plus 45 days | `interval` |

`recorded_month` must be usable in a query filter and `line_total_cents` in a query sort, still within that
same single statement.

On `Subscription`:

| field | type | value |
| --- | --- | --- |
| `usage_record_count` | integer | number of usage records |
| `pending_usage_count` | integer | number of usage records with `invoiced == false` |
| `pending_quantity` | integer | sum of `quantity` over usage records with `invoiced == false`, `0` when there are none |
| `latest_metric` | string | `metric` of the usage record with the greatest `recorded_at`, `nil` when there are none |
| `issued_invoice_count` | integer | number of invoices with `status == :issued` |
| `issued_total_cents` | integer | sum of `total_cents` over invoices with `status == :issued`, `0` when there are none |
| `plan_unit_cents` | integer | `unit_cents` of the linked `PlanRate` |
| `plan_included_units` | integer | `included_units` of the linked `PlanRate` |
| `average_issued_cents` | integer | `0` when `issued_invoice_count` is `0`, otherwise `issued_total_cents / issued_invoice_count` rounded half-up |
| `overage_cents` | integer | `billing_overage_cents(pending_quantity, plan_included_units, plan_unit_cents)`; SQL must contain `billing_overage_cents(` |
| `code_label` | string | `code` upper-cased |
| `monthly_label` | string | `monthly_cents` rendered as text; SQL must contain `::text` |

`pending_quantity` and `issued_total_cents` must both be usable directly in a query filter, and the whole set
above must load for every subscription of a tenant in one statement containing `count(` and `sum(`.

On `Invoice`: `line_count` (integer, number of invoice lines), `lines_total_cents` (integer, sum of
`amount_cents` over invoice lines, `0` when there are none), `balanced` (boolean, `total_cents ==
lines_total_cents`) and `number_label` (string, `number` lower-cased).

On `Tag`: `invoice_count` (integer, number of linked invoices) and `invoiced_cents` (integer, sum of
`total_cents` over linked invoices whose `status` is `:issued`, `0` when there are none). Both traverse the
many-to-many relationship and must load in one statement that references `"tenant_<slug>"."invoice_tags"`.

Read actions: `:search` returns the subscriptions whose `code` matches `pattern` **case-insensitively** using
SQL pattern matching (emitted SQL contains `ilike`); `:numbered` returns the invoices whose `number` matches
`pattern` **case-sensitively**; `:fuzzy` returns the subscriptions whose `code` has a PostgreSQL trigram
similarity to `term` strictly greater than `threshold` (emitted SQL contains `similarity(`).

### 6. Code interface on `Billing.Metering`

Expose exactly these functions on the domain (each also in its `!` form, each accepting a trailing options
list where the tenant is passed):

`register_organisation/3`, `list_organisations/0`, `define_plan_rate/3`, `list_plan_rates/0`,
`open_subscription/2`, `search_subscriptions/2`, `fuzzy_subscriptions/3`, `spend/3`, `record_usage/2`,
`issue_invoice/2`, `close_period/4`, `create_tag/2`, `tag_invoice/3`.

Positional arguments: `register_organisation(slug, name, plan_code)`,
`define_plan_rate(plan_code, unit_cents, included_units)`, `open_subscription(attrs)`,
`search_subscriptions(pattern)`, `fuzzy_subscriptions(term, threshold)`,
`spend(subscription_id, amount_cents)`, `record_usage(attrs)`, `issue_invoice(invoice)`,
`close_period(subscription_id, number, cap_cents)`, `create_tag(name)`, `tag_invoice(invoice_id, tag_id)`.

## Implementation Hints

- Project path: `/home/user/billing`.
- Everything must compile and run with `MIX_ENV=dev` and no network access.
- The verifier runs, from the project root: `pg-start`, then drops and recreates the `billing_dev` database,
  then `mix ash_postgres.create` and `mix ash_postgres.migrate`, and finally executes an ExUnit suite with
  `mix run`. Only your committed migrations are applied before the suite starts, so anything the suite needs
  beyond the two global tables must be provisioned by your code at runtime.
- Do not modify `Billing.Trace`, and do not change the `Billing.Repo` connection settings in
  `config/config.exs`.

