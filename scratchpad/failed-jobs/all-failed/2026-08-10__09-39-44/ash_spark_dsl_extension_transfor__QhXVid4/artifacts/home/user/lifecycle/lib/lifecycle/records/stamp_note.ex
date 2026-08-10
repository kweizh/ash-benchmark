defmodule Lifecycle.Records.StampNote do
  @moduledoc """
  A stand-alone `Ash.Resource.Change` that stamps "stamped" into the `:note`
  attribute of whatever resource it is attached to.
  """
  use Ash.Resource.Change

  @impl true
  def change(changeset, _opts, _context) do
    Ash.Changeset.force_change_attribute(changeset, :note, "stamped")
  end
end
