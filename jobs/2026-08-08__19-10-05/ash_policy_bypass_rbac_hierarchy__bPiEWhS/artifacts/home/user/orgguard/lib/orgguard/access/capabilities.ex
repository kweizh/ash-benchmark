defmodule OrgGuard.Access.Capabilities do
  @moduledoc false

  @role_capabilities %{
    viewer: [:read],
    editor: [:read, :write],
    auditor: [:read, :view_budget],
    unit_admin: [:read, :write, :delete, :relocate, :view_budget]
  }

  @doc """
  Returns the list of capabilities for a given role.
  """
  def capabilities_for_role(role) do
    Map.get(@role_capabilities, role, [])
  end

  @doc """
  Resolves the effective roles for an actor at a given org unit.

  Returns a map of %{role => true} for roles the actor holds at the org unit.
  """
  def effective_roles(actor, org_unit, all_assignments, all_org_units) do
    path = org_unit_path(org_unit, all_org_units)

    [:viewer, :editor, :auditor, :unit_admin]
    |> Enum.reduce(%{}, fn role, acc ->
      if holds_role?(actor, role, path, all_assignments) do
        Map.put(acc, role, true)
      else
        acc
      end
    end)
  end

  @doc """
  Returns the set of capabilities an actor has at a given org unit.
  """
  def capabilities_at(actor, org_unit, all_assignments, all_org_units) do
    actor
    |> effective_roles(org_unit, all_assignments, all_org_units)
    |> Map.keys()
    |> Enum.flat_map(&capabilities_for_role/1)
    |> MapSet.new()
  end

  @doc """
  Checks if an actor has a specific capability at a given org unit.
  """
  def has_capability?(actor, org_unit, capability, all_assignments, all_org_units) do
    capability in capabilities_at(actor, org_unit, all_assignments, all_org_units)
  end

  # Build the path from the given org_unit up to the root (nearest first).
  defp org_unit_path(org_unit, all_org_units) do
    build_path(org_unit, all_org_units, [])
  end

  defp build_path(nil, _all_org_units, acc), do: Enum.reverse(acc)

  defp build_path(org_unit, all_org_units, acc) do
    parent = find_parent(org_unit, all_org_units)
    build_path(parent, all_org_units, [org_unit | acc])
  end

  defp find_parent(%{parent_id: nil}, _all_org_units), do: nil

  defp find_parent(%{parent_id: parent_id}, all_org_units) do
    Enum.find(all_org_units, &(&1.id == parent_id))
  end

  # Determine if the actor holds a specific role, following the precedence rules.
  defp holds_role?(actor, role, path, all_assignments) do
    # Walk path from nearest to root, stop at first unit with any assignment for this role.
    {stopping_unit, assignments_at_unit} =
      Enum.find_value(path, fn unit ->
        relevant =
          Enum.filter(all_assignments, fn a ->
            a.user_id == actor.id and a.org_unit_id == unit.id and a.role == role
          end)

        if relevant != [], do: {unit, relevant}
      end)

    if stopping_unit == nil do
      # No assignment found on the path.
      false
    else
      # If any assignment at the stopping unit has effect: :deny, the actor does not hold the role.
      not Enum.any?(assignments_at_unit, &(&1.effect == :deny))
    end
  end
end
