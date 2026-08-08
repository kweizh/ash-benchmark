defmodule OrgGuard.Access.Checks.CanDestroyDocument do
  @moduledoc """
  A simple check that is true when the actor holds the `:delete`
  capability at the document's org unit.
  """
  use Ash.Policy.SimpleCheck

  alias OrgGuard.Access.Capabilities

  @impl true
  def describe(_opts), do: "org unit grants :delete capability"

  @impl true
  def match?(actor, %{changeset: %Ash.Changeset{data: data}}, _opts) do
    Capabilities.has_capability?(actor, data.org_unit_id, :delete)
  end

  def match?(_actor, _context, _opts), do: false
end
