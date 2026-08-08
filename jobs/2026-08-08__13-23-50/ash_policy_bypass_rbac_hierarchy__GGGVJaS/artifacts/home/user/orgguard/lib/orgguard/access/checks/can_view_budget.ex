defmodule OrgGuard.Access.Checks.CanViewBudget do
  @moduledoc """
  A filter check used in the `budget_cents` field policy — true for rows
  whose `org_unit_id` grants the actor the `:view_budget` capability.
  """
  use Ash.Policy.FilterCheck

  alias OrgGuard.Access.Capabilities

  @impl true
  def describe(_opts), do: "org unit grants :view_budget capability"

  @impl true
  def filter(actor, _authorizer, _opts) do
    allowed_ids = Capabilities.org_unit_ids_with_capability(actor, :view_budget)
    expr(org_unit_id in ^allowed_ids)
  end
end
