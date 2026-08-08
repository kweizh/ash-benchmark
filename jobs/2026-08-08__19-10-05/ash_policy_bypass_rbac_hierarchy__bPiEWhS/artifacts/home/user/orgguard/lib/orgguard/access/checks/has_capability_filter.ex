defmodule OrgGuard.Access.Checks.HasCapabilityFilter do
  @moduledoc """
  A filter check that determines if the actor has a given capability
  at the document's org_unit. This is used for read filtering.

  The filter/3 callback loads all role assignments and org units,
  then computes which org_unit_ids the actor has the given capability at,
  and returns a filter expression that restricts documents to those org units.
  """
  use Ash.Policy.FilterCheck

  require Ash.Query

  @impl true
  def describe(opts) do
    "actor has #{opts[:capability]} capability at the document's org_unit"
  end

  @impl true
  def filter(actor, _context, opts) do
    capability = opts[:capability]

    if actor == nil do
      expr(false)
    else
      # Load all role assignments and org units to determine which org_units
      # the actor has the required capability at.

      all_assignments =
        OrgGuard.Access.RoleAssignment
        |> Ash.Query.new()
        |> Ash.read!(authorize?: false)

      all_org_units =
        OrgGuard.Access.OrgUnit
        |> Ash.Query.new()
        |> Ash.read!(authorize?: false)

      allowed_org_unit_ids =
        all_org_units
        |> Enum.filter(fn org_unit ->
          OrgGuard.Access.Capabilities.has_capability?(
            actor,
            org_unit,
            capability,
            all_assignments,
            all_org_units
          )
        end)
        |> Enum.map(& &1.id)
        |> IO.inspect(label: "allowed_org_unit_ids")

      if allowed_org_unit_ids == [] do
        expr(false)
      else
        expr(org_unit_id in ^allowed_org_unit_ids)
      end
    end
  end
end
