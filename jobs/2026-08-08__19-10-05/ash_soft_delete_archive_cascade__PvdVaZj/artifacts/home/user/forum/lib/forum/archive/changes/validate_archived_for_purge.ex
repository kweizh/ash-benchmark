defmodule Forum.Archive.Changes.ValidateArchivedForPurge do
  @moduledoc """
  Validates that a record is archived before it can be purged.

  If `archived_at` is `nil`, adds an `Ash.Error.Changes.InvalidChanges` error
  with `fields: [:archived_at]` and message `"must be archived before it can be purged"`.
  """

  use Ash.Resource.Change

  @impl true
  def change(changeset, _opts, _context) do
    if changeset.data.archived_at == nil do
      Ash.Changeset.add_error(
        changeset,
        Ash.Error.Changes.InvalidChanges.exception(
          fields: [:archived_at],
          message: "must be archived before it can be purged"
        )
      )
    else
      changeset
    end
  end
end
