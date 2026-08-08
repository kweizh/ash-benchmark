defmodule OrgGuard.Access.Checks.CanReadOrgUnit do
  @moduledoc """
  A filter check scoping a `Document` read query to only the rows whose
  `org_unit_id` grants the actor the `:read` capability.
  """
  use Ash.Policy.FilterCheck

  alias OrgGuard.Access.Capabilities

  @impl true
  def describe(_opts), do: "org unit grants :read capability"

  @impl true
  def filter(actor, _authorizer, _opts) do
    allowed_ids = Capabilities.org_unit_ids_with_capability(actor, :read)
    expr(org_unit_id in ^allowed_ids)
  end
end
