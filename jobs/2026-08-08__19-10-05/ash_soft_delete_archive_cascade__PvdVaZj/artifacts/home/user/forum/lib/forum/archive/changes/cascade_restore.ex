defmodule Forum.Archive.Changes.CascadeRestore do
  @moduledoc """
  Restores a record and all of its descendants that share the same `archive_batch_id`.

  On a record that is not archived, nothing changes anywhere.
  On an archived record: the target's `archived_at` and `archive_batch_id` both become `nil`,
  and every descendant whose `archive_batch_id` equals the target's `archive_batch_id`
  (as it was immediately before the call) is restored the same way, recursively.

  Descendants carrying a different `archive_batch_id` are left exactly as they were.
  `:restore` never affects ancestors of the target.
  """

  use Ash.Resource.Change

  @impl true
  def change(changeset, _opts, _context) do
    record = changeset.data

    if record.archived_at == nil do
      # Not archived — no-op.
      changeset
    else
      batch_id = record.archive_batch_id

      changeset
      |> Ash.Changeset.force_change_attribute(:archived_at, nil)
      |> Ash.Changeset.force_change_attribute(:archive_batch_id, nil)
      |> Ash.Changeset.after_action(fn _changeset, result ->
        cascade_restore(result, batch_id)
      end)
    end
  end

  defp cascade_restore(record, batch_id) do
    resource = record.__struct__

    case resource do
      Forum.Content.Post ->
        restore_descendants_of_post(record, batch_id)

      Forum.Content.Comment ->
        restore_descendants_of_comment(record, batch_id)

      Forum.Content.Reaction ->
        {:ok, record}
    end
  end

  defp restore_descendants_of_post(post, batch_id) do
    domain = Ash.Resource.Info.domain(Forum.Content.Post)

    query =
      Forum.Content.Comment
      |> Ash.Query.for_read(:with_archived, %{})
      |> Ash.Query.filter(post_id == ^post.id and archive_batch_id == ^batch_id)

    case Ash.read(query, domain: domain, authorize?: false) do
      {:ok, comments} ->
        Enum.reduce_while(comments, {:ok, post}, fn comment, {:ok, _post} ->
          comment
          |> Ash.Changeset.new()
          |> Ash.Changeset.force_change_attribute(:archived_at, nil)
          |> Ash.Changeset.force_change_attribute(:archive_batch_id, nil)
          |> Ash.Changeset.for_update(:restore, %{})
          |> Ash.update(domain: domain, action: :restore, authorize?: false)
          |> case do
            {:ok, updated_comment} ->
              case restore_descendants_of_comment(updated_comment, batch_id) do
                {:ok, _} -> {:cont, {:ok, post}}
                {:error, error} -> {:halt, {:error, error}}
              end

            {:error, error} ->
              {:halt, {:error, error}}
          end
        end)

      {:error, error} ->
        {:error, error}
    end
  end

  defp restore_descendants_of_comment(comment, batch_id) do
    domain = Ash.Resource.Info.domain(Forum.Content.Comment)

    query =
      Forum.Content.Reaction
      |> Ash.Query.for_read(:with_archived, %{})
      |> Ash.Query.filter(comment_id == ^comment.id and archive_batch_id == ^batch_id)

    case Ash.read(query, domain: domain, authorize?: false) do
      {:ok, reactions} ->
        Enum.reduce_while(reactions, {:ok, comment}, fn reaction, {:ok, _comment} ->
          reaction
          |> Ash.Changeset.new()
          |> Ash.Changeset.force_change_attribute(:archived_at, nil)
          |> Ash.Changeset.force_change_attribute(:archive_batch_id, nil)
          |> Ash.Changeset.for_update(:restore, %{})
          |> Ash.update(domain: domain, action: :restore, authorize?: false)
          |> case do
            {:ok, _} -> {:cont, {:ok, comment}}
            {:error, error} -> {:halt, {:error, error}}
          end
        end)

      {:error, error} ->
        {:error, error}
    end
  end
end
