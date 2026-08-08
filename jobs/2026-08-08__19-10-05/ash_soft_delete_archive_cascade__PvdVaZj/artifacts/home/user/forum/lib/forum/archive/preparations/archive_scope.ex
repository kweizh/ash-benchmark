defmodule Forum.Archive.Preparations.ArchiveScope do
  @moduledoc """
  A shared preparation that scopes a read query based on archive status.

  This preparation is attached to the `:read`, `:archived`, and `:with_archived`
  actions of all three resources. It inspects the action name to determine which
  filter to apply:

    * `:read`          — only records where `archived_at` is `nil`
    * `:archived`      — only records where `archived_at` is not `nil`
    * `:with_archived` — no additional filter (returns both)
  """

  use Ash.Resource.Preparation

  @impl true
  def prepare(query, _opts, _context) do
    action = query.action

    case action.name do
      :read ->
        Ash.Query.filter(query, is_nil(archived_at))

      :archived ->
        Ash.Query.filter(query, not is_nil(archived_at))

      :with_archived ->
        query
    end
  end
end
