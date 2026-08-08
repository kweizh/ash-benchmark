defmodule ThreadGraph.Forum.Messages.AncestorMessages do
  @moduledoc false
  use Ash.Resource.ManualRelationship

  @impl true
  def load(messages, _opts, _context) do
    ThreadGraph.Forum.LoadCounter.bump(:ancestor_messages)

    # Build a map from message id to the message record (source messages)
    source_map = Map.new(messages, &{&1.id, &1})

    # Collect all ancestor ids transitively
    # Start with the parent_ids of the source messages
    frontier =
      messages
      |> Enum.map(& &1.parent_id)
      |> Enum.reject(&is_nil/1)
      |> Enum.uniq()
      |> Enum.reject(fn id -> Map.has_key?(source_map, id) end)

    # Fetch all ancestors transitively
    all_fetched = fetch_all_ancestors(frontier, %{}, MapSet.new())

    # Now build the chain for each source message
    result =
      Enum.map(messages, fn msg ->
        build_ancestor_chain(msg.parent_id, all_fetched, [], MapSet.new())
        |> Enum.reverse()
      end)

    {:ok, result}
  end

  defp fetch_all_ancestors([], fetched, _visited), do: fetched

  defp fetch_all_ancestors(ids, fetched, visited) do
    # Filter out already visited/fetched
    new_ids = Enum.reject(ids, fn id -> Map.has_key?(fetched, id) or MapSet.member?(visited, id) end)

    case new_ids do
      [] ->
        fetched

      ids_to_fetch ->
        visited = MapSet.union(visited, MapSet.new(ids_to_fetch))

        {:ok, filter} =
          Ash.Filter.parse_input(ThreadGraph.Forum.Message, %{id: [in: ids_to_fetch]})

        {:ok, fetched_messages} =
          ThreadGraph.Forum.Message
          |> Ash.Query.do_filter(filter)
          |> Ash.read(domain: ThreadGraph.Forum)

        new_fetched =
          Enum.reduce(fetched_messages, fetched, fn msg, acc ->
            Map.put(acc, msg.id, msg)
          end)

        # Get next level of parent_ids
        next_ids =
          fetched_messages
          |> Enum.map(& &1.parent_id)
          |> Enum.reject(&is_nil/1)
          |> Enum.uniq()
          |> Enum.reject(fn id -> Map.has_key?(new_fetched, id) or MapSet.member?(visited, id) end)

        fetch_all_ancestors(next_ids, new_fetched, visited)
    end
  end

  defp build_ancestor_chain(nil, _fetched, acc, _visited), do: acc

  defp build_ancestor_chain(parent_id, fetched, acc, visited) do
    if MapSet.member?(visited, parent_id) do
      acc
    else
      case Map.get(fetched, parent_id) do
        nil ->
          acc

        parent_msg ->
          build_ancestor_chain(
            parent_msg.parent_id,
            fetched,
            [parent_msg | acc],
            MapSet.put(visited, parent_id)
          )
      end
    end
  end
end
