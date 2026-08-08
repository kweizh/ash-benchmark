defmodule Forum.Archive.Changes.CascadeArchive do
  @moduledoc """
  Archives a record and all of its descendants that are not already archived.

  All newly archived records receive the same `archived_at` timestamp and the
  same `archive_batch_id`. Records that were already archived before this call
  are left untouched.

  When the target record is already archived, nothing changes anywhere.
  """

  use Ash.Resource.Change

  @impl true
  def change(changeset, _opts, _context) do
    record = changeset.data

    if record.archived_at != nil do
      # Already archived — no-op.
      changeset
    else
      batch_id = Ash.UUID.generate()
      now = DateTime.utc_now()

      changeset
      |> Ash.Changeset.force_change_attribute(:archived_at, now)
      |> Ash.Changeset.force_change_attribute(:archive_batch_id, batch_id)
      |> Ash.Changeset.after_action(fn _changeset, result ->
        cascade_archive(result, now, batch_id)
      end)
    end
  end

  defp cascade_archive(record, now, batch_id) do
    resource = record.__struct__

    case resource do
      Forum.Content.Post ->
        archive_descendants_of_post(record, now, batch_id)

      Forum.Content.Comment ->
        archive_descendants_of_comment(record, now, batch_id)

      Forum.Content.Reaction ->
        {:ok, record}
    end
  end

  defp archive_descendants_of_post(post, now, batch_id) do
    domain = Ash.Resource.Info.domain(Forum.Content.Post)

    query =
      Forum.Content.Comment
      |> Ash.Query.for_read(:with_archived, %{})
      |> Ash.Query.filter(post_id == ^post.id)

    case Ash.read(query, domain: domain, authorize?: false) do
      {:ok, comments} ->
        Enum.reduce_while(comments, {:ok, post}, fn comment, {:ok, _post} ->
          if comment.archived_at != nil do
            {:cont, {:ok, post}}
          else
            comment
            |> Ash.Changeset.new()
            |> Ash.Changeset.force_change_attribute(:archived_at, now)
            |> Ash.Changeset.force_change_attribute(:archive_batch_id, batch_id)
            |> Ash.Changeset.for_update(:restore, %{})
            |> Ash.update(domain: domain, action: :restore, authorize?: false)
            |> case do
              {:ok, updated_comment} ->
                case archive_descendants_of_comment(updated_comment, now, batch_id) do
                  {:ok, _} -> {:cont, {:ok, post}}
                  {:error, error} -> {:halt, {:error, error}}
                end

              {:error, error} ->
                {:halt, {:error, error}}
            end
          end
        end)

      {:error, error} ->
        {:error, error}
    end
  end

  defp archive_descendants_of_comment(comment, now, batch_id) do
    domain = Ash.Resource.Info.domain(Forum.Content.Comment)

    query =
      Forum.Content.Reaction
      |> Ash.Query.for_read(:with_archived, %{})
      |> Ash.Query.filter(comment_id == ^comment.id)

    case Ash.read(query, domain: domain, authorize?: false) do
      {:ok, reactions} ->
        Enum.reduce_while(reactions, {:ok, comment}, fn reaction, {:ok, _comment} ->
          if reaction.archived_at != nil do
            {:cont, {:ok, comment}}
          else
            reaction
            |> Ash.Changeset.new()
            |> Ash.Changeset.force_change_attribute(:archived_at, now)
            |> Ash.Changeset.force_change_attribute(:archive_batch_id, batch_id)
            |> Ash.Changeset.for_update(:restore, %{})
            |> Ash.update(domain: domain, action: :restore, authorize?: false)
            |> case do
              {:ok, _} -> {:cont, {:ok, comment}}
              {:error, error} -> {:halt, {:error, error}}
            end
          end
        end)

      {:error, error} ->
        {:error, error}
    end
  end
end
