defmodule Feed.Api do
  @moduledoc """
  The paging API layer that a mobile client's infinite-scroll would drive.

  Wraps the `Feed.Timeline.Activity` feed read actions with a cursor-based
  windowing API (`fetch/2`) that stays correct even as the underlying
  dataset is mutated between page fetches, plus two convenience walkers
  (`walk/2` and `walk_back/2`) that drive that API end to end.
  """

  alias Feed.Timeline.Activity

  @known_feeds [:feed, :public_feed, :hot_feed, :heat_feed, :author_feed]

  @doc """
  Fetches a single window of `feed_name`.

  `opts` may include:

    * `:limit` - how many records to return. Defaults to the feed action's
      own configured default limit.
    * `:cursor` - a cursor string previously returned as `:next_cursor` or
      `:prev_cursor`, used to continue paging in that direction.
    * `:author_id` - required when `feed_name` is `:author_feed`.

  See the moduledoc for the full behaviour contract.
  """
  @spec fetch(atom(), keyword()) :: {:ok, map()} | {:error, term()}
  def fetch(feed_name, opts \\ []) do
    with :ok <- validate_feed(feed_name),
         {:ok, args} <- build_args(feed_name, opts),
         pagination <- Ash.Resource.Info.action(Activity, feed_name).pagination,
         {:ok, limit} <- validate_limit(Keyword.get(opts, :limit), pagination),
         {:ok, cursor} <- validate_cursor(Keyword.get(opts, :cursor), feed_name) do
      do_fetch(feed_name, args, limit, cursor)
    end
  end

  @doc """
  Same as `fetch/2`, but raises on error.
  """
  @spec fetch!(atom(), keyword()) :: map()
  def fetch!(feed_name, opts \\ []) do
    case fetch(feed_name, opts) do
      {:ok, result} -> result
      {:error, error} -> raise "Feed.Api.fetch/2 failed: #{inspect(error)}"
    end
  end

  @doc """
  Walks `feed_name` forward from the very first window, following
  `:next_cursor` until there is none.

  Returns `{:ok, %{pages: pages, total: total}}` where `pages` is the list
  of windows visited (each window being the list of activity ids it
  contained, in feed order), in the order they were visited. An empty feed
  yields `%{pages: [[]], total: 0}`.
  """
  @spec walk(atom(), keyword()) :: {:ok, map()} | {:error, term()}
  def walk(feed_name, opts \\ []) do
    case fetch(feed_name, opts) do
      {:error, _} = error -> error
      {:ok, page} -> walk_forward(feed_name, opts, page, [ids(page)])
    end
  end

  @doc """
  Walks `feed_name` backward from the very last window, following
  `:prev_cursor` until there is none.

  Returns the same `{:ok, %{pages: pages, total: total}}` shape as
  `walk/2`, with `pages` in visit order (last window first).
  """
  @spec walk_back(atom(), keyword()) :: {:ok, map()} | {:error, term()}
  def walk_back(feed_name, opts \\ []) do
    case find_last_page(feed_name, opts) do
      {:error, _} = error -> error
      {:ok, page} -> walk_backward(feed_name, opts, page, [ids(page)])
    end
  end

  # -- fetch/2 helpers ------------------------------------------------------

  defp validate_feed(feed_name) when feed_name in @known_feeds, do: :ok
  defp validate_feed(feed_name), do: {:error, {:unknown_feed, feed_name}}

  defp build_args(:author_feed, opts) do
    case Keyword.get(opts, :author_id) do
      nil -> {:error, :author_id_required}
      author_id -> {:ok, %{author_id: author_id}}
    end
  end

  defp build_args(_feed_name, _opts), do: {:ok, %{}}

  defp validate_limit(nil, pagination), do: {:ok, pagination.default_limit}

  defp validate_limit(limit, pagination) when is_integer(limit) and limit > 0 do
    if pagination.max_page_size && limit > pagination.max_page_size do
      {:error, {:limit_too_large, pagination.max_page_size}}
    else
      {:ok, limit}
    end
  end

  defp validate_limit(_limit, _pagination), do: {:error, :invalid_limit}

  defp validate_cursor(nil, _feed_name), do: {:ok, nil}

  defp validate_cursor(cursor, feed_name) when is_binary(cursor) do
    case Feed.Cursor.decode(cursor) do
      {:ok, %{feed: ^feed_name, direction: direction, keyset: keyset}} ->
        {:ok, {direction, keyset}}

      {:ok, %{}} ->
        {:error, :cursor_feed_mismatch}

      {:error, _} = error ->
        error
    end
  end

  defp do_fetch(feed_name, args, limit, cursor) do
    page_opts = base_page_opts(limit, cursor)

    query =
      Activity
      |> Ash.Query.for_read(feed_name, args)
      |> Ash.Query.load([:reaction_count, :heat, :author])

    case Ash.read(query, page: page_opts) do
      {:ok, page} ->
        items = page.results
        {has_next, next_cursor} = next_info(feed_name, args, items)
        {has_prev, prev_cursor} = prev_info(feed_name, args, items)

        {:ok,
         %{
           items: items,
           next_cursor: next_cursor,
           prev_cursor: prev_cursor,
           total: page.count,
           has_next: has_next,
           has_prev: has_prev
         }}

      {:error, error} ->
        {:error, error}
    end
  end

  defp base_page_opts(limit, nil), do: [limit: limit, count: true]
  defp base_page_opts(limit, {:next, keyset}), do: [limit: limit, count: true, after: keyset]
  defp base_page_opts(limit, {:prev, keyset}), do: [limit: limit, count: true, before: keyset]

  defp next_info(_feed_name, _args, []), do: {false, nil}

  defp next_info(feed_name, args, items) do
    keyset = List.last(items).__metadata__.keyset
    has_next = exists_beyond?(feed_name, args, :after, keyset)

    cursor =
      if has_next do
        Feed.Cursor.encode(%{feed: feed_name, direction: :next, keyset: keyset})
      end

    {has_next, cursor}
  end

  defp prev_info(_feed_name, _args, []), do: {false, nil}

  defp prev_info(feed_name, args, items) do
    keyset = List.first(items).__metadata__.keyset
    has_prev = exists_beyond?(feed_name, args, :before, keyset)

    cursor =
      if has_prev do
        Feed.Cursor.encode(%{feed: feed_name, direction: :prev, keyset: keyset})
      end

    {has_prev, cursor}
  end

  defp exists_beyond?(feed_name, args, side, keyset) do
    query = Ash.Query.for_read(Activity, feed_name, args)
    page_opts = Keyword.put([limit: 1, count: false], side, keyset)

    case Ash.read(query, page: page_opts) do
      {:ok, %{results: results}} -> results != []
      {:error, _} -> false
    end
  end

  defp ids(page), do: Enum.map(page.items, & &1.id)

  # -- walk/2 and walk_back/2 helpers ---------------------------------------

  defp walk_forward(feed_name, opts, page, pages_acc) do
    if page.has_next do
      case fetch(feed_name, Keyword.put(opts, :cursor, page.next_cursor)) do
        {:error, _} = error ->
          error

        {:ok, next_page} ->
          walk_forward(feed_name, opts, next_page, pages_acc ++ [ids(next_page)])
      end
    else
      {:ok, %{pages: pages_acc, total: page.total}}
    end
  end

  defp find_last_page(feed_name, opts) do
    case fetch(feed_name, opts) do
      {:error, _} = error -> error
      {:ok, page} -> find_last_page(feed_name, opts, page)
    end
  end

  defp find_last_page(feed_name, opts, page) do
    if page.has_next do
      case fetch(feed_name, Keyword.put(opts, :cursor, page.next_cursor)) do
        {:error, _} = error -> error
        {:ok, next_page} -> find_last_page(feed_name, opts, next_page)
      end
    else
      {:ok, page}
    end
  end

  defp walk_backward(feed_name, opts, page, pages_acc) do
    if page.has_prev do
      case fetch(feed_name, Keyword.put(opts, :cursor, page.prev_cursor)) do
        {:error, _} = error ->
          error

        {:ok, prev_page} ->
          walk_backward(feed_name, opts, prev_page, pages_acc ++ [ids(prev_page)])
      end
    else
      {:ok, %{pages: pages_acc, total: page.total}}
    end
  end
end
