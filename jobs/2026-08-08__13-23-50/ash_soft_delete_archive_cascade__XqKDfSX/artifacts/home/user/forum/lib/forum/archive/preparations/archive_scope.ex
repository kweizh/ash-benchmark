defmodule Forum.Archive.Preparations.ArchiveScope do
  @moduledoc """
  Scopes a read action's results according to the `archived_at` attribute.

  Accepts a `:scope` option:

    * `:live` - only records where `archived_at` is `nil`.
    * `:archived` - only records where `archived_at` is not `nil`.
    * `:all` - no filtering is applied.

  This preparation is shared across all archivable resources and is
  attached to their `:read`, `:archived`, and `:with_archived` actions so
  that archived records never leak into an ordinary read, and so that the
  same scoping is applied wherever the resource is reached indirectly
  (relationship loads, aggregates, and filters that traverse a
  relationship), since those all default to using the destination
  resource's primary read action.
  """
  use Ash.Resource.Preparation

  @impl true
  def init(opts) do
    if opts[:scope] in [:live, :archived, :all] do
      {:ok, opts}
    else
      {:error, "scope must be one of :live, :archived, or :all, got: #{inspect(opts[:scope])}"}
    end
  end

  @impl true
  def prepare(query, opts, _context) do
    case opts[:scope] do
      :live -> Ash.Query.filter(query, is_nil(archived_at))
      :archived -> Ash.Query.filter(query, not is_nil(archived_at))
      :all -> query
    end
  end
end
