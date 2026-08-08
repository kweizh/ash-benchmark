defmodule Forum.Archive.Changes.CascadePurge do
  @moduledoc """
  Implements the cascading part of the `:purge` action for archivable
  resources: once a record has actually been removed from storage, every
  descendant (reached via the given child relationship, regardless of its
  own archived state) is purged too, recursively.

  Descendants are purged with a private context flag set so that the
  `:purge` action's "must be archived" validation is bypassed for them -
  only the top-level, user-invoked purge is required to target an archived
  record.

  ## Options

    * `:relationship` - the name of the has_many relationship to cascade
      the purge to, or `nil` if this resource has no children.
  """
  use Ash.Resource.Change

  @impl true
  def init(opts), do: {:ok, opts}

  @impl true
  def change(changeset, opts, _context) do
    Ash.Changeset.after_action(changeset, fn _changeset, result ->
      cascade(result, opts[:relationship])
      {:ok, result}
    end)
  end

  defp cascade(_record, nil), do: :ok

  defp cascade(record, relationship_name) do
    relationship = Ash.Resource.Info.relationship(record.__struct__, relationship_name)

    load_query =
      Ash.Query.for_read(relationship.destination, :with_archived, %{}, authorize?: false)

    record
    |> Ash.load!([{relationship_name, load_query}], authorize?: false)
    |> Map.get(relationship_name)
    |> Enum.each(fn child ->
      child
      |> Ash.Changeset.for_destroy(:purge, %{}, context: %{cascade_purge: true}, authorize?: false)
      |> Ash.destroy!()
    end)
  end
end
