defmodule Orchestra.Fleet.Changes.ReserveCapacity do
  @moduledoc """
  Validates that a node has enough free capacity for the requested number of
  slots, and if so reserves them.
  """
  use Ash.Resource.Change

  @impl true
  def change(changeset, _opts, _context) do
    slots = Ash.Changeset.get_argument(changeset, :slots)
    node = changeset.data

    if node.slots_used + slots > node.slots_total do
      Ash.Changeset.add_error(
        changeset,
        Ash.Error.Changes.InvalidChanges.exception(
          fields: [:slots],
          message:
            "node #{node.name} cannot supply #{slots} slot(s), only " <>
              "#{node.slots_total - node.slots_used} free"
        )
      )
    else
      changeset
      |> Ash.Changeset.force_change_attribute(:slots_used, node.slots_used + slots)
      |> Ash.Changeset.force_change_attribute(:state, :reserved)
    end
  end
end
