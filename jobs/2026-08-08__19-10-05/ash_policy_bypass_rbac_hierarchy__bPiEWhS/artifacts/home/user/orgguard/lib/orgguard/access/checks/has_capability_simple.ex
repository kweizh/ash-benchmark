defmodule OrgGuard.Access.Checks.HasCapabilitySimple do
  @moduledoc """
  A simple check that determines if the actor has a given capability
  at a specific org_unit. Used for create, update, destroy, and relocate actions.

  For create, the org_unit is taken from the changeset's org_unit_id.
  For update/destroy, the org_unit is taken from the record's org_unit.
  For relocate, checks both the source and target org_units.
  """
  use Ash.Policy.SimpleCheck

  require Ash.Query

  @impl true
  def match?(actor, context, opts) do
    capability = opts[:capability]

    if actor == nil do
      false
    else
      all_assignments =
        OrgGuard.Access.RoleAssignment
        |> Ash.Query.new()
        |> Ash.read!(authorize?: false)

      all_org_units =
        OrgGuard.Access.OrgUnit
        |> Ash.Query.new()
        |> Ash.read!(authorize?: false)

      org_unit_ids = resolve_org_unit_ids(context)

      Enum.all?(org_unit_ids, fn org_unit_id ->
        org_unit = Enum.find(all_org_units, &(&1.id == org_unit_id))

        if org_unit == nil do
          false
        else
          OrgGuard.Access.Capabilities.has_capability?(
            actor,
            org_unit,
            capability,
            all_assignments,
            all_org_units
          )
        end
      end)
    end
  end

  @impl true
  def describe(opts) do
    "actor has #{opts[:capability]} capability at the relevant org_unit(s)"
  end

  defp resolve_org_unit_ids(context) do
    cond do
      # For create: get org_unit_id from changeset
      context.changeset && context.changeset.action_type == :create ->
        org_unit_id =
          Ash.Changeset.get_attribute(context.changeset, :org_unit_id) ||
            Ash.Changeset.get_data(context.changeset, :org_unit_id)

        if org_unit_id, do: [org_unit_id], else: []

      # For update/destroy: get org_unit from the record
      context.changeset && context.changeset.action_type in [:update, :destroy] ->
        org_unit_id =
          case Map.get(context.changeset.data, :org_unit) do
            %{id: id} -> id
            _ -> Map.get(context.changeset.data, :org_unit_id)
          end

        if org_unit_id, do: [org_unit_id], else: []

      # For generic action (relocate): get both source and target
      context.action.type == :action ->
        document_id = context.action_input && context.action_input.arguments[:document_id]
        target_org_unit_id = context.action_input && context.action_input.arguments[:target_org_unit_id]
        source_org_unit_id = get_document_org_unit_id(context, document_id)

        [source_org_unit_id, target_org_unit_id] |> Enum.filter(&(&1 != nil))

      true ->
        []
    end
  end

  defp get_org_unit_id(record) do
    case Map.get(record, :org_unit) do
      %{id: id} -> id
      _ -> Map.get(record, :org_unit_id)
    end
  end

  defp get_document_org_unit_id(_context, document_id) do
    if document_id do
      case OrgGuard.Access.Document
           |> Ash.Query.new()
           |> Ash.Query.do_filter(
             Ash.Filter.parse_input!(OrgGuard.Access.Document, id: document_id)
           )
           |> Ash.read(authorize?: false) do
        {:ok, [document]} -> get_org_unit_id(document)
        _ -> nil
      end
    end
  end
end
