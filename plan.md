# Ash Framework Research Plan

## 1. Library Overview

### Description
The **Ash Framework** is a declarative, extensible, and resource-oriented framework for building applications in Elixir. Unlike traditional MVC frameworks that focus on database tables and controllers, Ash models your entire application as a set of declarative **Resources**. It leverages Elixir's powerful compile-time metaprogramming to automatically derive database schemas, API endpoints (JSON:API, GraphQL), authorization policies, and data validations from these resource definitions.

### Ecosystem Role
Ash integrates seamlessly with the existing Elixir ecosystem rather than replacing it:
* **Phoenix / LiveView**: Ash acts as the business logic and data layer. Extensions like `ash_phoenix` and `ash_authentication_phoenix` provide forms, helpers, and authentication components directly integrated with LiveView.
* **Ecto**: Ash uses Ecto under the hood for its database operations (via `ash_postgres`), but abstracts the repository and changeset layers into declarative DSL blocks.
* **APIs**: It eliminates boilerplate by automatically generating REST (via `ash_json_api`) and GraphQL (via `ash_graphql`) APIs directly from resource definitions.
* **Alternative to MVC**: It competes with or complements standard MVC patterns by moving business logic, access control, and data validation into a single, cohesive, declarative resource layer.

### Installation
To install Ash Framework v3 in an Elixir project, add the following dependencies to your `mix.exs`:

```elixir
def deps do
  [
    {:ash, "~> 3.0"},
    {:picosat_elixir, "~> 0.2"} # Required for the Ash SAT solver policy engine
  ]
end
```

Using **Igniter** (the recommended setup tool for Ash v3) makes installation and configuration automatic:

```bash
# Install the Igniter archive if not already installed
mix archive.install hex igniter_new

# Create a new Elixir project with Ash pre-configured
mix igniter.new helpdesk --install ash && cd helpdesk

# Or install Ash in an existing project
mix igniter.install ash
```

### Project Setup
Setting up an Ash application involves three main steps:

1. **Configure Ash Domains**: Add your domains to `config/config.exs` so Ash can locate your resources and compile-time configurations:
   ```elixir
   config :helpdesk,
     ash_domains: [Helpdesk.Support]
   ```

2. **Define a Domain**: Create a domain module to group related resources and define code interfaces:
   ```elixir
   # lib/helpdesk/support.ex
   defmodule Helpdesk.Support do
     use Ash.Domain, otp_app: :helpdesk

     resources do
       resource Helpdesk.Support.Ticket do
         define :open_ticket, action: :open, args: [:subject]
         define :close_ticket, action: :close
         define :get_ticket, action: :read, get_by: [:id]
       end
     end
   end
   ```

3. **Configure the Data Layer**: Ensure your data layer (e.g., ETS for in-memory or PostgreSQL for persistence) is correctly set up. For PostgreSQL, you configure `ash_postgres` and point your resources to your repo:
   ```elixir
   # config/config.exs
   config :helpdesk, ecto_repos: [Helpdesk.Repo]
   ```

---

## 2. Core Primitives & APIs

### Resources
Resources are the core building blocks in Ash. A resource is an Elixir module that uses `use Ash.Resource` and contains declarative DSL blocks defining its data, actions, relationships, and metadata.

```elixir
defmodule Helpdesk.Support.Ticket do
  use Ash.Resource,
    otp_app: :helpdesk,
    domain: Helpdesk.Support,
    data_layer: Ash.DataLayer.Ets

  attributes do
    uuid_primary_key :id
    attribute :subject, :string, allow_nil?: false
    attribute :status, :atom, default: :open, constraints: [one_of: [:open, :closed]]
  end

  actions do
    defaults [:read, :destroy]

    create :open do
      accept [:subject]
    end

    update :close do
      accept []
      change set_attribute(:status, :closed)
    end
  end

  relationships do
    belongs_to :representative, Helpdesk.Support.Representative
  end
end
```
* **Attributes**: Define the fields stored on the resource.
* **Relationships**: Define associations (e.g., `belongs_to`, `has_many`, `many_to_many`).
* **Calculations**: Define read-only computed values (e.g., `full_name`).
* **Aggregates**: Define database-level summary queries over relationships (e.g., `count`, `sum`).

### Actions
Actions define the operations that can be performed on a resource. Ash supports five types of actions:
1. **Create**: For creating new records (e.g., `create :open`).
2. **Read**: For querying records (e.g., `read :read`).
3. **Update**: For modifying existing records (e.g., `update :close`).
4. **Destroy**: For deleting records.
5. **Generic**: For running arbitrary business logic that doesn't map directly to CRUD operations.

Actions can be customized with **Validations** (run before execution) and **Changes** (modify the changeset during execution):

```elixir
create :open do
  accept [:subject]
  validate present(:subject)
  change set_attribute(:status, :open)
end
```

### Domains
In Ash v3, resources are grouped into **Domains** (which replaces `Ash.Api` from Ash v2). The Domain acts as a boundary for related resources, exposes public APIs, and configures cross-cutting concerns like global timeouts and default authorization policies.

```elixir
defmodule Helpdesk.Support do
  use Ash.Domain, otp_app: :helpdesk

  resources do
    resource Helpdesk.Support.Ticket
    resource Helpdesk.Support.Representative
  end

  execution do
    timeout :timer.seconds(30)
  end
end
```

### Data Layers
Ash is data-layer agnostic. You specify the data layer when defining the resource:
* **ETS (`Ash.DataLayer.Ets`)**: In-memory storage, ideal for testing, prototyping, or transient state.
* **Mnesia (`Ash.DataLayer.Mnesia`)**: Distributed in-memory/disk storage built into Erlang.
* **PostgreSQL (`ash_postgres`)**: Robust SQL-backed persistence layer leveraging Ecto.
* **Simple (`Ash.DataLayer.Simple`)**: No data layer; used for embedded resources or mock data.

### Querying & Changesets
Interactions with resources are mediated by `Ash.Query` (for reads) and `Ash.Changeset` (for writes).

```elixir
# Creating a record
ticket =
  Helpdesk.Support.Ticket
  |> Ash.Changeset.for_create(:open, %{subject: "My internet is down"})
  |> Ash.create!()

# Querying with filters and sorting
tickets =
  Helpdesk.Support.Ticket
  |> Ash.Query.filter(status == :open)
  |> Ash.Query.sort(inserted_at: :desc)
  |> Ash.Query.load([:representative])
  |> Ash.read!()
```

### Code Interfaces
Code interfaces allow you to expose resource actions as standard Elixir functions on the Domain or Resource module, hiding the complexity of constructing queries and changesets manually.

```elixir
# Exposing functions on the Domain
defmodule Helpdesk.Support do
  use Ash.Domain, otp_app: :helpdesk

  resources do
    resource Helpdesk.Support.Ticket do
      define :open_ticket, action: :open, args: [:subject]
      define :close_ticket, action: :close
    end
  end
end

# Calling the code interface
{:ok, ticket} = Helpdesk.Support.open_ticket("Server offline")
```

---

## 3. Real-World Use Cases

Ash is highly effective for building complex, enterprise-grade backends where security, maintainability, and API flexibility are paramount.

### Multi-Tenant SaaS Backends
Ash has native support for **multitenancy** (attribute-based or schema-based). It automatically scopes all database queries and writes to the active tenant without requiring developers to manually append `where tenant_id = ...` to every query.

### Complex Authorization and Policy Systems
Using `Ash.Policy.Authorizer`, developers can build fine-grained Role-Based Access Control (RBAC) and Attribute-Based Access Control (ABAC) systems. Ash's policy engine compiles rules into a SAT solver, which can optimize queries to automatically filter out rows a user shouldn't see rather than throwing a `Forbidden` error after reading them.

### Rapid API Development
For apps requiring REST or GraphQL interfaces, extensions like `ash_json_api` and `ash_graphql` automatically expose resource actions, calculations, and relationships over HTTP, adhering strictly to JSON:API or GraphQL specifications.

### CQRS and Event-Driven Orchestration
Using `Ash.Notifier` (e.g., with PubSub) and **Reactor** (Ash's declarative workflow orchestrator), developers can build complex event-driven architectures where operations trigger background jobs, state transitions, or external API integrations in a transactional, rollback-safe manner.

---

## 4. Developer Friction Points

While Ash provides unparalleled productivity, it introduces unique challenges and learning curves that developers must navigate.

### DSL Complexity & "Magic"
Because Ash relies heavily on compile-time macros (via the `Spark` library), the framework can feel like "magic" to beginners. It requires a shift from writing imperative Elixir code to configuring declarative DSL blocks. Autocomplete and "jump-to-definition" in IDEs can sometimes be limited or flakey due to the extensive use of metaprogramming.

### Ash v2 to v3 Migration
Ash v3 introduced breaking architectural changes:
* **Api vs. Domain**: `Ash.Api` was completely replaced by `Ash.Domain`.
* **Explicit Domains**: Resources must now explicitly declare their domain option in `use Ash.Resource, domain: ...`, and functions like `Ash.Changeset.for_create/4` require passing the domain.
* **Atomics**: Writes in v3 are atomic by default, which changes how validations and custom changes are executed.

### Understanding Policies and the SAT Solver
Designing policies can be tricky. Because Ash uses a SAT solver to evaluate policy checks, a misconfigured policy can lead to compilation errors or unexpected authorization failures. Developers must understand the difference between `authorize_if`, `forbid_if`, and `authorize_unless`, and how policies compose across reads and writes.

### Calculations vs. Aggregates
* **Aggregates** are executed directly in the database (e.g., generating SQL `COUNT` or `SUM` queries), making them highly performant but restricted to supported database operations.
* **Calculations** can be expression-based (run in SQL) or module-based (run in-memory in Elixir). Module-based calculations are incredibly flexible but require explicitly declaring dependencies via the `load/3` callback so Ash can pre-fetch required fields.

### Debugging & Cryptic Compile-Time Errors
When a DSL block has syntax or logic errors (such as referencing a non-existent relationship or mismatching argument types), Spark can produce cryptic, deeply nested compilation errors. Furthermore, because Ash pipelines run through validations, changes, authorizers, and notifiers, runtime stack traces can be dominated by framework internals, making it harder to locate the source of a bug.

---

## 5. Evaluation Ideas

The following complex, real-world tasks can be used to evaluate an AI agent's proficiency with Ash Framework v3.

### Idea 1: Multi-Tenant Subscription-Based Resource Allocation
* **Goal**: Implement a multi-tenant SaaS backend where each `Tenant` has a maximum active `Project` limit based on their subscription plan. When a user attempts to create a new `Project`, the create action must validate that the tenant's current active project count does not exceed their subscription plan's limit.
* **Complexity**: Requires configuring multi-tenancy on resources, implementing a database-level `count` aggregate on the `Tenant` resource to count active projects, and writing a custom changeset validation (`Ash.Changeset.Validation`) that compares the aggregate count against the subscription limit at write-time.
* **Validation**: ExUnit tests that create multiple tenants with different subscription tiers, attempt to exceed limits, assert that validation errors are correctly raised, and verify complete multi-tenant isolation.

### Idea 2: Fine-Grained Collaborative Document Authorization (RBAC/ABAC)
* **Goal**: Build a collaborative document editor backend where `Document` resources have a many-to-many relationship with `User` resources through a `DocumentUser` join table containing roles (`owner`, `editor`, `viewer`). Implement field-level policies so that only the `owner` can read/update the `internal_notes` attribute, `editors` can read/update `content`, and `viewers` can only read `content`.
* **Complexity**: Demands advanced use of `Ash.Policy.Authorizer`, configuring many-to-many relationships, defining custom policy checks (e.g., traversing relationships or using `relates_to_actor_via`), and implementing fine-grained `field_policies` on attributes.
* **Validation**: ExUnit tests asserting that unauthorized users are blocked from reading or writing restricted fields (returning `nil` or raising forbidden errors), while authorized users are permitted, across all roles.

### Idea 3: Transactional Order Checkout Workflow with Reactor
* **Goal**: Create a robust, transactional order checkout workflow using `Ash.Reactor` or complex generic actions. The workflow must: 1. Verify stock availability on an `Inventory` resource; 2. Reserve stock; 3. Process a mock payment transaction; 4. If payment fails, roll back the stock reservation; 5. If successful, mark the `Order` as completed and trigger an asynchronous notification.
* **Complexity**: Requires integrating `Ash.Reactor` or writing transactional action hooks (`after_action`/`before_action` with rollback handlers), managing complex state transitions, and handling failures gracefully.
* **Validation**: ExUnit tests simulating successful and failed payment paths, verifying that inventory is correctly decremented or restored, and asserting that notifications are dispatched only on success.

### Idea 4: Dynamic Cart Pricing Engine with Custom Module Calculations
* **Goal**: Implement a dynamic shopping cart pricing calculation. The calculation must load all `CartItem` resources, apply tiered pricing discounts based on quantity (e.g., buy 10+ get 10% off), check for active promotions on a `Coupon` resource, and calculate estimated tax based on the user's geographical region.
* **Complexity**: Requires implementing a custom module calculation (using the `Ash.Calculation` behavior with `load/3` and `calculate/3` callbacks) because the logic requires procedurally loading related resources (coupons, tax rates) and executing conditional Elixir code that cannot be represented as a simple SQL expression.
* **Validation**: ExUnit tests verifying calculations across multiple cart configurations, varying quantities, valid/invalid coupons, and different tax regions, asserting that the calculated totals match expected values exactly.

### Idea 5: Cascading Soft-Delete with Global Filters and Archive Recovery
* **Goal**: Implement a soft-delete mechanism for a blog system (`Post` and `Comment` resources). Soft-deleted posts and comments must remain in the database with a `deleted_at` timestamp. By default, all read actions must filter out soft-deleted items. Provide an admin-only read action `read_archived` to view deleted items, a `destroy` action that soft-deletes a post and cascades soft-delete to its comments, and a `restore` action that recursively restores them.
* **Complexity**: Involves custom read preparations (`Ash.Resource.Preparation` or inline `prepare`), overriding default filters, writing custom update actions that behave as soft-deletes, and cascading database operations in Elixir/Ash.
* **Validation**: ExUnit tests asserting that soft-deleted items are hidden from standard reads, visible only to authorized admin reads, and that restoring a post correctly restores all associated comments.

---

## 6. Sources

1. [Ash Framework HexDocs](https://hexdocs.pm/ash/) - Official documentation, guides, and reference material for Ash.
2. [Ash Framework GitHub Repository](https://github.com/ash-project/ash) - Core repository containing source code and issue discussions.
3. [Ash v3 Upgrade Guide](https://hexdocs.pm/ash/upgrading-to-3-0.html) - Complete breakdown of breaking changes and architectural updates from Ash v2.
4. [Ash Calculations Guide](https://hexdocs.pm/ash/calculations.html) - In-depth explanation of expression-based and module-based calculations.
5. [Ash Policies Guide](https://hexdocs.pm/ash/policies.html) - Comprehensive reference for configuring declarative access control and policy checks.
6. [Ash Code Interfaces Guide](https://hexdocs.pm/ash/code-interfaces.html) - Documentation on exposing resource actions as clean, type-safe Elixir functions.
