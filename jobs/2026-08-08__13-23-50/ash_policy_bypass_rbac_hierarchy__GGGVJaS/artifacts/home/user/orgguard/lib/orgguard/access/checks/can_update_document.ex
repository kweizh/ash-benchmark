defmodule OrgGuard.Access.Checks.CanUpdateDocument do
  @moduledoc """
  A simple check that is true when the actor holds the `:write` capability
  at the document's org unit, and — if `budget_cents` is being changed —
  also holds the `:view_budget` capability there.
  """
  use Ash.Policy.SimpleCheck

  alias OrgGuard.Access.Capabilities

  @impl true
  def describe(_opts),
    do: "org unit grants :write (and :view_budget when changing budget_cents)"

  @impl true
  def match?(actor, %{changeset: %Ash.Changeset{data: data} = changeset}, _opts) do
    org_unit_id = data.org_unit_id

    Capabilities.has_capability?(actor, org_unit_id, :write) and
      (not Ash.Changeset.changing_attribute?(changeset, :budget_cents) or
         Capabilities.has_capability?(actor, org_unit_id, :view_budget))
  end

  def match?(_actor, _context, _opts), do: false
end
