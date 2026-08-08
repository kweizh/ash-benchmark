defmodule Forum.Archive.Changes.CascadeRestore do
  @moduledoc """
  Implements the `:restore` action for archivable resources.

  If the record being restored is not archived, nothing happens.

  Otherwise, the record's `archived_at`/`archive_batch_id` are cleared, and
  every descendant (reached via the given child relationship) whose
  `archive_batch_id` matched the target's `archive_batch_id` *before* this
  call is restored the same way, recursively - achieved by invoking that
  relationship's own `:restore` action on each matching child, since every
  resource's `:restore` action is wired up with this same change, pointing
  at its own children.

  Descendants carrying a different `archive_batch_id` (i.e. archived
  independently, at a different time) are left untouched.

  ## Options

    * `:relationship` - the name of the has_many relationship to cascade
      the restore to, or `nil` if this resource has no children.
  """
  use Ash.Resource.Change

  @impl true
  def init(opts), do: {:ok, opts}

  @impl true
  def change(changeset, opts, _context) do
    case Map.get(changeset.data, :archived_at) do
      nil ->
        changeset

      _archived_at ->
        batch_id = Map.get(changeset.data, :archive_batch_id)

        changeset
        |> Ash.Changeset.force_change_attribute(:archived_at, nil)
        |> Ash.Changeset.force_change_attribute(:archive_batch_id, nil)
        |> Ash.Changeset.after_action(fn _changeset, result ->
          cascade(result, opts[:relationship], batch_id)
          {:ok, result}
        end)
    end
  end

  defp cascade(_record, nil, _batch_id), do: :ok

  defp cascade(record, relationship_name, batch_id) do
    relationship = Ash.Resource.Info.relationship(record.__struct__, relationship_name)

    load_query =
      Ash.Query.for_read(relationship.destination, :with_archived, %{}, authorize?: false)

    record
    |> Ash.load!([{relationship_name, load_query}], authorize?: false)
    |> Map.get(relationship_name)
    |> Enum.filter(&(&1.archive_batch_id == batch_id))
    |> Enum.each(fn child ->
      child
      |> Ash.Changeset.for_update(:restore, %{}, authorize?: false)
      |> Ash.update!()
    end)
  end
end
