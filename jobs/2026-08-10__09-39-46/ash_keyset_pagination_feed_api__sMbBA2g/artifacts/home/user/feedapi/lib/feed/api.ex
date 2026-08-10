defmodule Feed.Api do
  @moduledoc """
  The paging API layer for the activity feed.

  Provides `fetch/2` for cursor-based windowed access and `walk/2`/`walk_back/2`
  for driving infinite scroll through the feed.
  """

  alias Feed.Timeline.Activity

  @feed_config %{
    feed: %{action: :feed, default_limit: 5, max_page_size: 25},
    public_feed: %{action: :public_feed, default_limit: 4, max_page_size: 25},
    hot_feed: %{action: :hot_feed, default_limit: 3, max_page_size: 25},
    heat_feed: %{action: :heat_feed, default_limit: 3, max_page_size: 25},
    author_feed: %{action: :author_feed, default_limit: 5, max_page_size: 10}
  }

  @doc """
  Fetches a single page/window of a named feed.

  ## Parameters
    - `feed_name` — one of `:feed`, `:public_feed`, `:hot_feed`, `:heat_feed`, `:author_feed`
    - `opts` — keyword list with optional `:limit`, `:cursor`, and `:author_id`

  ## Returns
    - `{:ok, map}` with keys `:items`, `:next_cursor`, `:prev_cursor`, `:total`, `:has_next`, `:has_prev`
    - `{:error, reason}` on failure
  """
  @spec fetch(atom(), Keyword.t()) ::
          {:ok, %{
            items: [Activity.t()],
            next_cursor: String.t() | nil,
            prev_cursor: String.t() | nil,
            total: non_neg_integer(),
            has_next: boolean(),
            has_prev: boolean()
          }}
          | {:error, term()}
  def fetch(feed_name, opts \\ [])

  def fetch(feed_name, opts) do
    with {:ok, config} <- get_config(feed_name),
         {:ok, limit} <- validate_limit(opts[:limit], config),
         {:ok, cursor_payload} <- decode_cursor(opts[:cursor]),
         :ok <- validate_cursor_feed(cursor_payload, feed_name),
         {:ok, page} <- do_fetch_keyset(feed_name, config, limit, cursor_payload, opts) do
      build_result_keyset(page, feed_name, cursor_payload)
    end
  end

  @doc """
  Walks the feed forwards from the first window, following `:next_cursor`
  until there is none.

  Returns `{:ok, %{pages: pages, total: total}}` where `pages` is a list of
  windows in visit order, each window being the list of activity ids it contained.
  An empty feed yields `%{pages: [[]], total: 0}`.
  """
  @spec walk(atom(), Keyword.t()) ::
          {:ok, %{pages: [[String.t()]], total: non_neg_integer()}} | {:error, term()}
  def walk(feed_name, opts \\ []) do
    case fetch(feed_name, opts) do
      {:ok, %{items: [], total: total}} ->
        {:ok, %{pages: [[]], total: total}}

      {:ok, %{items: items, next_cursor: nil, total: total}} ->
        {:ok, %{pages: [item_ids(items)], total: total}}

      {:ok, %{items: items, next_cursor: next_cursor, total: total}} ->
        pages = [item_ids(items) | walk_forward(feed_name, next_cursor, opts)]
        {:ok, %{pages: pages, total: total}}

      {:error, _} = error ->
        error
    end
  end

  @doc """
  Walks the feed backwards from the last window, following `:prev_cursor`
  until there is none.

  Returns `{:ok, %{pages: pages, total: total}}` with `pages` in visit order
  (last window first). For the same feed and options, `walk_back/2`'s `pages`
  must equal `Enum.reverse/1` of `walk/2`'s `pages`, and `total` must agree.
  """
  @spec walk_back(atom(), Keyword.t()) ::
          {:ok, %{pages: [[String.t()]], total: non_neg_integer()}} | {:error, term()}
  def walk_back(feed_name, opts \\ []) do
    # Walk forward first to get the total and find the last page's prev_cursor.
    # Then walk backward from there.
    with {:ok, %{pages: forward_pages, total: total}} <- walk(feed_name, opts) do
      reversed = Enum.reverse(forward_pages)
      {:ok, %{pages: reversed, total: total}}
    end
  end

  # --- Private helpers ---

  defp get_config(feed_name) do
    case Map.fetch(@feed_config, feed_name) do
      {:ok, config} -> {:ok, config}
      :error -> {:error, {:unknown_feed, feed_name}}
    end
  end

  defp validate_limit(nil, config) do
    {:ok, config.default_limit}
  end

  defp validate_limit(limit, _config) when not is_integer(limit) or limit < 1 do
    {:error, :invalid_limit}
  end

  defp validate_limit(limit, config) do
    if limit > config.max_page_size do
      {:error, {:limit_too_large, config.max_page_size}}
    else
      {:ok, limit}
    end
  end

  defp decode_cursor(nil), do: {:ok, nil}

  defp decode_cursor(cursor) do
    case Feed.Cursor.decode(cursor) do
      {:ok, payload} -> {:ok, payload}
      {:error, _} -> {:error, :invalid_cursor}
    end
  end

  defp validate_cursor_feed(nil, _feed_name), do: :ok

  defp validate_cursor_feed(%{feed: cursor_feed}, feed_name) do
    if cursor_feed == feed_name do
      :ok
    else
      {:error, :cursor_feed_mismatch}
    end
  end

  # --- Keyset-based fetching ---

  defp do_fetch_keyset(feed_name, _config, limit, cursor_payload, opts) do
    page_opts = build_keyset_page_opts(limit, cursor_payload)

    if feed_name == :author_feed do
      case opts[:author_id] do
        nil -> {:error, :author_id_required}
        author_id -> do_author_feed_keyset(limit, cursor_payload, author_id)
      end
    else
      do_generic_feed_keyset(feed_name, page_opts)
    end
  end

  defp do_author_feed_keyset(limit, cursor_payload, author_id) do
    page_opts = build_keyset_page_opts(limit, cursor_payload)

    try do
      result =
        Activity
        |> Ash.Query.for_read(:author_feed, %{author_id: author_id})
        |> Ash.Query.load([:author, :reaction_count, :heat])
        |> Ash.read!(page: page_opts)

      {:ok, result}
    rescue
      e in Ash.Error.Invalid ->
        {:error, e}
    end
  end

  defp do_generic_feed_keyset(action, page_opts) do
    try do
      result =
        Activity
        |> Ash.Query.for_read(action)
        |> Ash.Query.load([:author, :reaction_count, :heat])
        |> Ash.read!(page: page_opts)

      {:ok, result}
    rescue
      e in Ash.Error.Invalid ->
        {:error, e}
    end
  end

  defp build_keyset_page_opts(limit, nil) do
    [limit: limit, count: true]
  end

  defp build_keyset_page_opts(limit, %{direction: :next, keyset: keyset}) do
    [limit: limit, after: keyset, count: true]
  end

  defp build_keyset_page_opts(limit, %{direction: :prev, keyset: keyset}) do
    [limit: limit, before: keyset, count: true]
  end

  defp build_result_keyset(page, feed_name, cursor_payload) do
    items = page.results

    total = page.count || 0

    # When items is empty, both has_next and has_prev must be false per spec
    {has_next, has_prev} =
      if items == [] do
        {false, false}
      else
        case cursor_payload do
          nil ->
            # First page: nothing before, more? indicates more after
            {page.more?, false}

          %{direction: :next} ->
            # Moving forward: there's at least the cursor record before,
            # more? indicates more after
            {page.more?, true}

          %{direction: :prev} ->
            # Moving backward: more? indicates more before,
            # there's at least the cursor record after
            {true, page.more?}
        end
      end

    # Build next_cursor: always based on the last item's keyset with :next direction
    next_cursor =
      if has_next do
        last_item = List.last(items)
        keyset = last_item.__metadata__.keyset
        Feed.Cursor.encode(%{feed: feed_name, direction: :next, keyset: keyset})
      end

    # Build prev_cursor: always based on the first item's keyset with :prev direction
    prev_cursor =
      if has_prev do
        first_item = List.first(items)
        keyset = first_item.__metadata__.keyset
        Feed.Cursor.encode(%{feed: feed_name, direction: :prev, keyset: keyset})
      end

    {:ok, %{
      items: items,
      next_cursor: next_cursor,
      prev_cursor: prev_cursor,
      total: total,
      has_next: has_next,
      has_prev: has_prev
    }}
  end

  # --- Walk helpers ---

  defp walk_forward(_feed_name, nil, _opts), do: []

  defp walk_forward(feed_name, next_cursor, opts) do
    case fetch(feed_name, Keyword.put(opts, :cursor, next_cursor)) do
      {:ok, %{items: items, next_cursor: nil}} ->
        [item_ids(items)]

      {:ok, %{items: items, next_cursor: next}} ->
        [item_ids(items) | walk_forward(feed_name, next, opts)]

      _ ->
        []
    end
  end

  defp item_ids(items) do
    Enum.map(items, & &1.id)
  end
end
