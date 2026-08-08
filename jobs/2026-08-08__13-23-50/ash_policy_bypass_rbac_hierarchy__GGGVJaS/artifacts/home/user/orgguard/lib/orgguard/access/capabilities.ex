defmodule OrgGuard.Access.Capabilities do
  @moduledoc """
  Resolves the set of capabilities an actor holds at a given org unit,
  implementing the hierarchical grant/deny resolution described in the
  project requirements:

    1. Build the path from the org unit up to the root (nearest first).
    2. For each role independently, walk that path and stop at the first
       unit that carries at least one `RoleAssignment` for the actor with
       that role.
    3. If no unit on the path carries such an assignment, the actor does
       not hold that role at the target unit.
    4. If the stopping unit carries any assignment for the actor/role with
       `effect: :deny`, the actor does not hold the role — even if an
       ancestor granted it.
    5. Otherwise the actor holds the role.

  The actor's capabilities are the union of the capabilities of every role
  held at the target org unit.
  """

  alias OrgGuard.Access.{OrgUnit, RoleAssignment}

  @roles [:viewer, :editor, :auditor, :unit_admin]

  @role_capabilities %{
    viewer: [:read],
    editor: [:read, :write],
    auditor: [:read, :view_budget],
    unit_admin: [:read, :write, :delete, :relocate, :view_budget]
  }

  @doc "Whether `actor` holds `capability` at the given org unit."
  @spec has_capability?(term(), term(), atom()) :: boolean()
  def has_capability?(actor, org_unit_id, capability) do
    capability in capabilities(actor, org_unit_id)
  end

  @doc "The set of capabilities `actor` holds at the given org unit."
  @spec capabilities(term(), term()) :: [atom()]
  def capabilities(nil, _org_unit_id), do: []
  def capabilities(_actor, nil), do: []

  def capabilities(actor, org_unit_id) do
    path = org_unit_path(org_unit_id)
    assignments = role_assignments_for_user(actor.id)

    @roles
    |> Enum.filter(&role_held_on_path?(&1, path, assignments))
    |> Enum.flat_map(&Map.fetch!(@role_capabilities, &1))
    |> Enum.uniq()
  end

  @doc "All org unit ids at which `actor` holds `capability`."
  @spec org_unit_ids_with_capability(term(), atom()) :: [term()]
  def org_unit_ids_with_capability(actor, capability) do
    Enum.filter(all_org_unit_ids(), &has_capability?(actor, &1, capability))
  end

  defp role_held_on_path?(role, path, assignments) do
    Enum.reduce_while(path, false, fn org_unit_id, _acc ->
      case Enum.filter(assignments, &(&1.org_unit_id == org_unit_id and &1.role == role)) do
        [] -> {:cont, false}
        matches -> {:halt, not Enum.any?(matches, &(&1.effect == :deny))}
      end
    end)
  end

  defp org_unit_path(org_unit_id) do
    build_path(org_unit_id, org_units_by_id(), [])
  end

  defp build_path(nil, _units, acc), do: Enum.reverse(acc)

  defp build_path(org_unit_id, units, acc) do
    case Map.fetch(units, org_unit_id) do
      {:ok, unit} -> build_path(unit.parent_id, units, [org_unit_id | acc])
      :error -> Enum.reverse(acc)
    end
  end

  defp org_units_by_id do
    OrgUnit
    |> Ash.read!(authorize?: false)
    |> Map.new(&{&1.id, &1})
  end

  defp all_org_unit_ids do
    org_units_by_id() |> Map.keys()
  end

  defp role_assignments_for_user(user_id) do
    RoleAssignment
    |> Ash.read!(authorize?: false)
    |> Enum.filter(&(&1.user_id == user_id))
  end
end
