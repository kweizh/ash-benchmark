defmodule OrgGuard.Access.Checks.CanRelocateDocument do
  @moduledoc """
  A simple check that is true when the actor holds the `:relocate`
  capability at both the document's current org unit and the target org
  unit named by the `:relocate` action's arguments.
  """
  use Ash.Policy.SimpleCheck

  alias OrgGuard.Access.Capabilities

  @impl true
  def describe(_opts), do: "org unit grants :relocate capability on both org units"

  @impl true
  def match?(actor, %{action_input: %Ash.ActionInput{} = input}, _opts) do
    document_id = Ash.ActionInput.get_argument(input, :document_id)
    target_org_unit_id = Ash.ActionInput.get_argument(input, :target_org_unit_id)

    case fetch_org_unit_id(document_id) do
      {:ok, current_org_unit_id} ->
        Capabilities.has_capability?(actor, current_org_unit_id, :relocate) and
          Capabilities.has_capability?(actor, target_org_unit_id, :relocate)

      :error ->
        false
    end
  end

  def match?(_actor, _context, _opts), do: false

  defp fetch_org_unit_id(nil), do: :error

  defp fetch_org_unit_id(document_id) do
    case Ash.get(OrgGuard.Access.Document, document_id, authorize?: false) do
      {:ok, document} -> {:ok, document.org_unit_id}
      _ -> :error
    end
  end
end
