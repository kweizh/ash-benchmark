defmodule Orchestra.Rollout.Changes.ReleaseReservation do
  @moduledoc false

  use Ash.Resource.Change

  alias Ash.Changeset
  alias Orchestra.Rollout.Trace

  @impl true
  def change(changeset, _opts, _context) do
    original = Changeset.get_argument(changeset, :changeset)

    old_slots =
      case original do
        %{data: %{slots_used: value}} -> value
        _ -> 0
      end

    changeset = Changeset.change_attribute(changeset, :slots_used, old_slots)

    changeset =
      if old_slots == 0 do
        Changeset.change_attribute(changeset, :state, :idle)
      else
        changeset
      end

    Trace.record({:reserve_undo, changeset.data.name})

    changeset
  end
end
