defmodule Forum.Archive.Preparations.ArchiveScope do
  @moduledoc """
  Preparation to scope reads to archived or live records.
  """
  use Ash.Resource.Preparation

  @impl true
  def prepare(query, _opts, _context) do
    case query.action.name do
      :read ->
        Ash.Query.filter(query, is_nil(archived_at))

      :archived ->
        Ash.Query.filter(query, not is_nil(archived_at))

      :with_archived ->
        query

      _ ->
        query
    end
  end
end
