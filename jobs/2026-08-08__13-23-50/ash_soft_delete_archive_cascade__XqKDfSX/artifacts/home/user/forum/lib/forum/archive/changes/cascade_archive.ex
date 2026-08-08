defmodule Forum.Archive.Changes.CascadeArchive do
  @moduledoc """
  Implements the `:archive` action for archivable resources.

  If the record being archived is already archived, nothing happens (the
  existing `archived_at`/`archive_batch_id` are left untouched, and nothing
  is cascaded).

  Otherwise, the record is stamped with an `archived_at` timestamp and an
  `archive_batch_id` (generated fresh unless one was handed down from an
  ancestor's archive operation, via private context), and the same
  generation is cascaded to the given child relationship by invoking that
  relationship's own `:archive` action on each child - which is what makes
  this recurse all the way down the content tree, since each resource's
  `:archive` action is wired up with this same change, pointing at its own
  children.

  ## Options

    * `:relationship` - the name of the has_many relationship to cascade
      the archive to, or `nil` if this resource has no children.
  """
  use Ash.Resource.Change

  @impl true
  def init(opts), do: {:ok, opts}

  @impl true
  def change(changeset, opts, _context) do
    if is_nil(Map.get(changeset.data, :archived_at)) do
      {archived_at, batch_id} = generation(changeset)

      changeset
      |> Ash.Changeset.force_change_attribute(:archived_at, archived_at)
      |> Ash.Changeset.force_change_attribute(:archive_batch_id, batch_id)
      |> Ash.Changeset.after_action(fn _changeset, result ->
        cascade(result, opts[:relationship], archived_at, batch_id)
        {:ok, result}
      end)
    else
      changeset
    end
  end

  defp generation(changeset) do
    case changeset.context do
      %{cascade_archive: %{archived_at: archived_at, batch_id: batch_id}} ->
        {archived_at, batch_id}

      _ ->
        {DateTime.utc_now(), Ash.UUID.generate()}
    end
  end

  defp cascade(_record, nil, _archived_at, _batch_id), do: :ok

  defp cascade(record, relationship_name, archived_at, batch_id) do
    relationship = Ash.Resource.Info.relationship(record.__struct__, relationship_name)

    load_query =
      Ash.Query.for_read(relationship.destination, :with_archived, %{}, authorize?: false)

    record
    |> Ash.load!([{relationship_name, load_query}], authorize?: false)
    |> Map.get(relationship_name)
    |> Enum.each(fn child ->
      child
      |> Ash.Changeset.for_destroy(
        :archive,
        %{},
        context: %{cascade_archive: %{archived_at: archived_at, batch_id: batch_id}},
        authorize?: false
      )
      |> Ash.destroy!()
    end)
  end
end
