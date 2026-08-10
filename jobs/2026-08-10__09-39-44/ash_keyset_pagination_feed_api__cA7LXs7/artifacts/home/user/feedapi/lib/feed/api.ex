defmodule Feed.Api do
  @moduledoc """
  The paging API layer that a mobile client's infinite-scroll would drive.

  `fetch/2` returns a single window of a feed together with opaque cursors
  for the next and previous windows.  `walk/2` and `walk_back/2` drive the
  feed forward and backward respectively, collecting every page.
  """

  alias Feed.Timeline.Activity

  @supported_feeds [:feed, :public_feed, :hot_feed, :heat_feed, :author_feed]

  @load [:author, :reaction_count, :heat]

  # -------------------------------------------------------------------------
  # Public API
  # -------------------------------------------------------------------------

  @doc """
  Fetches a single window of the named feed.

  Returns `{:ok, map}` on success where the map has exactly the keys
  `:items`, `:next_cursor`, `:prev_cursor`, `:total`, `:has_next` and
  `:has_prev`.
  """
  @spec fetch(atom(), keyword()) ::
          {:ok, map()}
          | {:error, term()}
  def fetch(feed_name, opts \\ [])

  def fetch(feed_name, _opts) when feed_name not in @supported_feeds do
    {:error, {:unknown_feed, feed_name}}
  end

  def fetch(feed_name, opts) do
    with :ok <- require_author_id(feed_name, opts),
         {:ok, limit} <- validate_limit(feed_name, opts),
         {:ok, cursor} <- decode_and_check_feed(feed_name, opts) do
      do_fetch(feed_name, opts, limit, cursor)
    end
  end

  @doc """
  Drives infinite scroll forwards from the first window, following
  `:next_cursor` until there is none.
  """
  @spec walk(atom(), keyword()) :: {:ok, %{pages: [[String.t()]], total: non_neg_integer()}} | {:error, term()}
  def walk(feed_name, opts \\ []) do
    walk_forward(feed_name, Keyword.delete(opts, :cursor), nil, [], nil)
  end

  @doc """
  Drives infinite scroll backwards from the last window, following
  `:prev_cursor` until there is none.
  """
  @spec walk_back(atom(), keyword()) :: {:ok, %{pages: [[String.t()]], total: non_neg_integer()}} | {:error, term()}
  def walk_back(feed_name, opts \\ []) do
    opts = Keyword.delete(opts, :cursor)

    case walk_to_last(feed_name, opts, nil, nil) do
      {:ok, %{last: last, total: total}} ->
        walk_backward(feed_name, opts, last, [], total)

      {:error, error} ->
        {:error, error}
    end
  end

  # -------------------------------------------------------------------------
  # fetch implementation
  # -------------------------------------------------------------------------

  defp require_author_id(:author_feed, opts) do
    case Keyword.fetch(opts, :author_id) do
      {:ok, author_id} when is_binary(author_id) and byte_size(author_id) > 0 -> :ok
      _ -> {:error, :author_id_required}
    end
  end

  defp require_author_id(_feed_name, _opts), do: :ok

  defp validate_limit(feed_name, opts) do
    case Keyword.fetch(opts, :limit) do
      :error ->
        {:ok, nil}

      {:ok, limit} ->
        max = max_page_size(feed_name)

        cond do
          not is_integer(limit) or limit <= 0 ->
            {:error, :invalid_limit}

          limit > max ->
            {:error, {:limit_too_large, max}}

          true ->
            {:ok, limit}
        end
    end
  end

  defp decode_and_check_feed(feed_name, opts) do
    case Keyword.fetch(opts, :cursor) do
      :error ->
        {:ok, nil}

      {:ok, cursor} when is_binary(cursor) ->
        case Feed.Cursor.decode(cursor) do
          {:ok, %{feed: ^feed_name} = payload} ->
            {:ok, payload}

          {:ok, _other_feed} ->
            {:error, :cursor_feed_mismatch}

          {:error, :invalid_cursor} ->
            {:error, :invalid_cursor}
        end

      {:ok, _} ->
        {:error, :invalid_cursor}
    end
  end

  defp do_fetch(feed_name, opts, limit, cursor) do
    page_opts =
      []
      |> maybe_put(:limit, limit)
      |> maybe_put(:count, true)
      |> maybe_put_cursor(cursor)

    case call_feed(feed_name, opts, page_opts, @load) do
      {:ok, page} ->
        build_result(feed_name, opts, page, cursor)

      {:error, error} ->
        {:error, error}
    end
  end

  defp build_result(feed_name, opts, page, cursor) do
    items = page.results

    {has_next, has_prev} = compute_bounds(feed_name, opts, items, page, cursor)

    next_cursor =
      if has_next and items != [] do
        items
        |> List.last()
        |> keyset_of()
        |> then(&Feed.Cursor.encode(%{feed: feed_name, direction: :next, keyset: &1}))
      end

    prev_cursor =
      if has_prev and items != [] do
        items
        |> List.first()
        |> keyset_of()
        |> then(&Feed.Cursor.encode(%{feed: feed_name, direction: :prev, keyset: &1}))
      end

    {:ok,
     %{
       items: items,
       next_cursor: next_cursor,
       prev_cursor: prev_cursor,
       total: page.count || 0,
       has_next: has_next,
       has_prev: has_prev
     }}
  end

  defp compute_bounds(_feed_name, _opts, [], _page, _cursor) do
    {false, false}
  end

  defp compute_bounds(feed_name, opts, items, page, cursor) do
    first_keyset = items |> List.first() |> keyset_of()
    last_keyset = items |> List.last() |> keyset_of()

    case cursor_direction(cursor) do
      nil ->
        # First window — nothing before it.
        {page.more?, false}

      :next ->
        has_prev = has_records?(feed_name, opts, :before, first_keyset)
        {page.more?, has_prev}

      :prev ->
        has_next = has_records?(feed_name, opts, :after, last_keyset)
        {has_next, page.more?}
    end
  end

  defp cursor_direction(nil), do: nil
  defp cursor_direction(%{direction: dir}), do: dir

  defp has_records?(feed_name, opts, direction, keyset) do
    page_opts = [{direction, keyset}, limit: 1]

    case call_feed(feed_name, opts, page_opts, nil) do
      {:ok, page} -> page.results != []
      {:error, _} -> false
    end
  end

  # -------------------------------------------------------------------------
  # walk implementation
  # -------------------------------------------------------------------------

  defp walk_forward(feed_name, opts, cursor, pages, total) do
    fetch_opts = if cursor, do: Keyword.put(opts, :cursor, cursor), else: opts

    case fetch(feed_name, fetch_opts) do
      {:ok, result} ->
        page_ids = Enum.map(result.items, & &1.id)
        pages = pages ++ [page_ids]
        total = total || result.total

        if result.has_next do
          walk_forward(feed_name, opts, result.next_cursor, pages, total)
        else
          {:ok, %{pages: pages, total: total}}
        end

      {:error, error} ->
        {:error, error}
    end
  end

  # -------------------------------------------------------------------------
  # walk_back implementation
  # -------------------------------------------------------------------------

  defp walk_to_last(feed_name, opts, cursor, total) do
    fetch_opts = if cursor, do: Keyword.put(opts, :cursor, cursor), else: opts

    case fetch(feed_name, fetch_opts) do
      {:ok, result} ->
        total = total || result.total

        if result.has_next do
          walk_to_last(feed_name, opts, result.next_cursor, total)
        else
          {:ok, %{last: result, total: total}}
        end

      {:error, error} ->
        {:error, error}
    end
  end

  defp walk_backward(feed_name, opts, result, pages, total) do
    page_ids = Enum.map(result.items, & &1.id)
    pages = pages ++ [page_ids]

    if result.has_prev do
      fetch_opts = Keyword.put(opts, :cursor, result.prev_cursor)

      case fetch(feed_name, fetch_opts) do
        {:ok, prev_result} ->
          walk_backward(feed_name, opts, prev_result, pages, total)

        {:error, error} ->
          {:error, error}
      end
    else
      {:ok, %{pages: pages, total: total}}
    end
  end

  # -------------------------------------------------------------------------
  # Helpers
  # -------------------------------------------------------------------------

  defp call_feed(feed_name, opts, page_opts, load) do
    feed_opts = [page: page_opts]
    feed_opts = if load, do: Keyword.put(feed_opts, :load, load), else: feed_opts

    if feed_name == :author_feed do
      author_id = Keyword.fetch!(opts, :author_id)
      Feed.Timeline.author_feed(author_id, feed_opts)
    else
      apply(Feed.Timeline, feed_name, [feed_opts])
    end
  end

  defp max_page_size(feed_name) do
    Activity
    |> Ash.Resource.Info.action(feed_name)
    |> Map.get(:pagination)
    |> Map.get(:max_page_size)
  end

  defp keyset_of(record) do
    record.__metadata__[:keyset]
  end

  defp maybe_put(opts, _key, nil), do: opts
  defp maybe_put(opts, key, value), do: Keyword.put(opts, key, value)

  defp maybe_put_cursor(opts, nil), do: opts
  defp maybe_put_cursor(opts, %{direction: :next, keyset: keyset}), do: Keyword.put(opts, :after, keyset)
  defp maybe_put_cursor(opts, %{direction: :prev, keyset: keyset}), do: Keyword.put(opts, :before, keyset)
end
