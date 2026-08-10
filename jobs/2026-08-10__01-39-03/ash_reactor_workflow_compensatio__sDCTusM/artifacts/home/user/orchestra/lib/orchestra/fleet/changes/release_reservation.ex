defmodule Orchestra.Fleet.Changes.ReleaseReservation do
  @moduledoc """
  Reverses a previously reserved amount of capacity on a node. Used as the
  `undo_action` for the `:reserve` update action.

  The original changeset used to perform the reservation is passed in via the
  `:changeset` argument (this is how `Ash.Reactor` undo works), and we pull
  the originally reserved slot count back out of it.
  """
  use Ash.Resource.Change

  alias Orchestra.Rollout.Trace

  @impl true
  def change(changeset, _opts, _context) do
    slots = extract_slots(Ash.Changeset.get_argument(changeset, :changeset))
    node = changeset.data

    new_used = max(node.slots_used - slots, 0)
    new_state = if new_used <= 0, do: :idle, else: node.state

    Trace.record({:reserve_undo, node.name})

    changeset
    |> Ash.Changeset.force_change_attribute(:slots_used, new_used)
    |> Ash.Changeset.force_change_attribute(:state, new_state)
  end

  defp extract_slots(%Ash.Changeset{} = original),
    do: Ash.Changeset.get_argument(original, :slots) || 0

  defp extract_slots(_), do: 0
end
