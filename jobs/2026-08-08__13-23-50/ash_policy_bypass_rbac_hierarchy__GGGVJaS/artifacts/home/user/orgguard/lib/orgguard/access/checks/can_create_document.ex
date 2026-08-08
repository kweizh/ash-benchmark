defmodule OrgGuard.Access.Checks.CanCreateDocument do
  @moduledoc """
  A simple check that is true when the actor holds the `:write` capability
  at the org unit named by the changeset's `org_unit_id`.
  """
  use Ash.Policy.SimpleCheck

  alias OrgGuard.Access.Capabilities

  @impl true
  def describe(_opts), do: "org unit (from org_unit_id) grants :write capability"

  @impl true
  def match?(actor, %{changeset: %Ash.Changeset{} = changeset}, _opts) do
    org_unit_id = Ash.Changeset.get_attribute(changeset, :org_unit_id)
    Capabilities.has_capability?(actor, org_unit_id, :write)
  end

  def match?(_actor, _context, _opts), do: false
end
