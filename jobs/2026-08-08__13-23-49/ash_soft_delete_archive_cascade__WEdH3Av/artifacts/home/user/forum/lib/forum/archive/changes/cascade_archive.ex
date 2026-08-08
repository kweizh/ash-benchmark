defmodule Forum.Archive.Changes.CascadeArchive do
  @moduledoc """
  Change to cascade archiving to descendants.
  """
  use Ash.Resource.Change
  require Ash.Query

  @impl true
  def change(changeset, _opts, _context) do
    if not is_nil(changeset.data.archived_at) do
      # Target is already archived, change nothing.
      changeset
    else
      batch_id = changeset.context[:archive_batch_id] || Ash.UUID.generate()
      archived_at = changeset.context[:archived_at] || DateTime.utc_now()

      changeset =
        changeset
        |> Ash.Changeset.force_change_attribute(:archived_at, archived_at)
        |> Ash.Changeset.force_change_attribute(:archive_batch_id, batch_id)

      Ash.Changeset.before_action(changeset, fn changeset ->
        resource = changeset.resource

        # Cascade to comments if Post
        if Ash.Resource.Info.relationship(resource, :comments) do
          parent_id = changeset.data.id

          comments =
            Forum.Content.Comment
            |> Ash.Query.for_read(:read, %{})
            |> Ash.Query.filter(post_id == ^parent_id)
            |> Ash.read!(authorize?: false)

          for comment <- comments do
            comment
            |> Ash.Changeset.for_destroy(:archive, %{},
                 context: %{archive_batch_id: batch_id, archived_at: archived_at},
                 authorize?: false
               )
            |> Ash.destroy!(authorize?: false)
          end
        end

        # Cascade to reactions if Comment
        if Ash.Resource.Info.relationship(resource, :reactions) do
          parent_id = changeset.data.id

          reactions =
            Forum.Content.Reaction
            |> Ash.Query.for_read(:read, %{})
            |> Ash.Query.filter(comment_id == ^parent_id)
            |> Ash.read!(authorize?: false)

          for reaction <- reactions do
            reaction
            |> Ash.Changeset.for_destroy(:archive, %{},
                 context: %{archive_batch_id: batch_id, archived_at: archived_at},
                 authorize?: false
               )
            |> Ash.destroy!(authorize?: false)
          end
        end

        changeset
      end)
    end
  end
end
