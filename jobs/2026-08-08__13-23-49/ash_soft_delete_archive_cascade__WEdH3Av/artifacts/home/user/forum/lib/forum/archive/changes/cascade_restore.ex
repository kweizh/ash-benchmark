defmodule Forum.Archive.Changes.CascadeRestore do
  @moduledoc """
  Change to cascade restoring to descendants.
  """
  use Ash.Resource.Change
  require Ash.Query

  @impl true
  def change(changeset, _opts, _context) do
    if is_nil(changeset.data.archived_at) do
      # Record is not archived, do nothing.
      changeset
    else
      batch_id = changeset.data.archive_batch_id

      changeset =
        changeset
        |> Ash.Changeset.force_change_attribute(:archived_at, nil)
        |> Ash.Changeset.force_change_attribute(:archive_batch_id, nil)

      Ash.Changeset.before_action(changeset, fn changeset ->
        resource = changeset.resource

        if not is_nil(batch_id) do
          # Cascade to comments if Post
          if Ash.Resource.Info.relationship(resource, :comments) do
            parent_id = changeset.data.id

            comments =
              Forum.Content.Comment
              |> Ash.Query.for_read(:with_archived, %{})
              |> Ash.Query.filter(post_id == ^parent_id and archive_batch_id == ^batch_id)
              |> Ash.read!(authorize?: false)

            for comment <- comments do
              Ash.update!(comment, action: :restore, authorize?: false)
            end
          end

          # Cascade to reactions if Comment
          if Ash.Resource.Info.relationship(resource, :reactions) do
            parent_id = changeset.data.id

            reactions =
              Forum.Content.Reaction
              |> Ash.Query.for_read(:with_archived, %{})
              |> Ash.Query.filter(comment_id == ^parent_id and archive_batch_id == ^batch_id)
              |> Ash.read!(authorize?: false)

            for reaction <- reactions do
              Ash.update!(reaction, action: :restore, authorize?: false)
            end
          end
        end

        changeset
      end)
    end
  end
end
