defmodule ThreadGraph.Forum.Messages.LinkedMessages do
  @moduledoc false
  use Ash.Resource.ManualRelationship

  @impl true
  def load(messages, _opts, _context) do
    ThreadGraph.Forum.LoadCounter.bump(:linked_messages)

    source_ids = Enum.map(messages, & &1.id)

    # Fetch all links from source messages
    {:ok, base_filter} =
      Ash.Filter.parse_input(ThreadGraph.Forum.MessageLink, %{from_message_id: [in: source_ids]})

    {:ok, all_links} =
      ThreadGraph.Forum.MessageLink
      |> Ash.Query.do_filter(base_filter)
      |> Ash.read(domain: ThreadGraph.Forum)

    # Build adjacency map
    adjacency = build_adjacency(all_links)

    # Discover all reachable nodes through BFS, fetching links as needed
    all_reachable = discover_all_reachable(source_ids, adjacency)

    # Fetch all reachable messages
    reachable_messages =
      case MapSet.size(all_reachable) do
        0 ->
          %{}

        _ ->
          reachable_list = MapSet.to_list(all_reachable)

          {:ok, msg_filter} =
            Ash.Filter.parse_input(ThreadGraph.Forum.Message, %{id: [in: reachable_list]})

          {:ok, fetched} =
            ThreadGraph.Forum.Message
            |> Ash.Query.do_filter(msg_filter)
            |> Ash.read(domain: ThreadGraph.Forum)

          Map.new(fetched, &{&1.id, &1})
      end

    # Compute BFS distances from each source
    result =
      Enum.map(messages, fn source ->
        bfs_from_source(source.id, adjacency, reachable_messages)
      end)

    {:ok, result}
  end

  defp build_adjacency(links) do
    Enum.reduce(links, %{}, fn link, acc ->
      Map.update(acc, link.from_message_id, [link.to_message_id], fn existing ->
        [link.to_message_id | existing]
      end)
    end)
  end

  defp discover_all_reachable(source_ids, adjacency) do
    discover_bfs(source_ids, adjacency, MapSet.new(), MapSet.new(source_ids))
  end

  defp discover_bfs([], _adjacency, _visited, all_reachable), do: all_reachable

  defp discover_bfs(frontier, adjacency, visited, all_reachable) do
    visited = MapSet.union(visited, MapSet.new(frontier))

    next_ids =
      Enum.flat_map(frontier, fn id ->
        Map.get(adjacency, id, [])
      end)
      |> Enum.reject(fn id -> MapSet.member?(visited, id) end)
      |> Enum.uniq()

    all_reachable = MapSet.union(all_reachable, MapSet.new(next_ids))

    # Check if any of the next_ids have adjacency we haven't fetched yet
    unfetched = Enum.reject(next_ids, fn id -> Map.has_key?(adjacency, id) end)

    adjacency =
      case unfetched do
        [] ->
          adjacency

        ids ->
          {:ok, link_filter} =
            Ash.Filter.parse_input(ThreadGraph.Forum.MessageLink, %{from_message_id: [in: ids]})

          {:ok, new_links} =
            ThreadGraph.Forum.MessageLink
            |> Ash.Query.do_filter(link_filter)
            |> Ash.read(domain: ThreadGraph.Forum)

          Map.merge(adjacency, build_adjacency(new_links))
      end

    discover_bfs(next_ids, adjacency, visited, all_reachable)
  end

  defp bfs_from_source(source_id, adjacency, reachable_messages) do
    bfs_queue([{source_id, 0}], %{}, MapSet.new([source_id]), adjacency, reachable_messages)
    |> Enum.sort_by(fn msg ->
      dist = msg.__metadata__[:hop_distance] || 0
      {dist, msg.position, msg.id}
    end)
  end

  defp bfs_queue([], distances, _visited, _adjacency, reachable_messages) do
    distances
    |> Enum.map(fn {id, dist} ->
      msg = Map.get(reachable_messages, id)
      if msg do
        Ash.Resource.put_metadata(msg, :hop_distance, dist)
      end
    end)
    |> Enum.reject(&is_nil/1)
  end

  defp bfs_queue([{id, dist} | rest], distances, visited, adjacency, reachable_messages) do
    distances =
      if dist == 0 do
        distances
      else
        Map.put_new(distances, id, dist)
      end

    next_nodes =
      Map.get(adjacency, id, [])
      |> Enum.reject(fn next_id -> MapSet.member?(visited, next_id) end)

    visited = Enum.reduce(next_nodes, visited, fn next_id, acc -> MapSet.put(acc, next_id) end)

    new_queue = rest ++ Enum.map(next_nodes, fn next_id -> {next_id, dist + 1} end)

    bfs_queue(new_queue, distances, visited, adjacency, reachable_messages)
  end
end
