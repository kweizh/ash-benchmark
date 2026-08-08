defmodule ThreadGraph.Forum.Messages.LinkedMessages do
  @moduledoc """
  Implements the `linked_messages` manual relationship on
  `ThreadGraph.Forum.Message`.

  For each source message (independently of the others), the value is
  every message reachable in one or more hops through the directed graph
  formed by `ThreadGraph.Forum.MessageLink` edges (regardless of `kind`),
  each associated with its minimum hop distance. The source message is
  never included, even when a cycle makes it reachable.
  """
  use Ash.Resource.ManualRelationship

  alias ThreadGraph.Forum.LoadCounter
  alias ThreadGraph.Forum.Message
  alias ThreadGraph.Forum.MessageLink

  @impl true
  def load(sources, _opts, context) do
    LoadCounter.bump(:linked_messages)

    read_opts = [
      domain: context.domain || ThreadGraph.Forum,
      actor: context.actor,
      tenant: context.tenant,
      authorize?: context.authorize? || false
    ]

    with {:ok, all_messages} <- Ash.read(Message, read_opts),
         {:ok, all_links} <- Ash.read(MessageLink, read_opts) do
      by_id = Map.new(all_messages, &{&1.id, &1})

      edges =
        Enum.reduce(all_links, %{}, fn link, acc ->
          Map.update(acc, link.from_message_id, [link.to_message_id], &[
            link.to_message_id | &1
          ])
        end)

      result = Map.new(sources, fn source -> {source.id, reachable_from(source, edges, by_id)} end)

      {:ok, result}
    end
  end

  defp reachable_from(source, edges, by_id) do
    source.id
    |> bfs_distances(edges)
    |> Enum.reject(fn {id, _dist} -> id == source.id end)
    |> Enum.flat_map(fn {id, dist} ->
      case Map.fetch(by_id, id) do
        {:ok, message} -> [{dist, message}]
        :error -> []
      end
    end)
    |> Enum.sort_by(fn {dist, message} -> {dist, message.position, message.id} end)
    |> Enum.map(fn {_dist, message} -> message end)
  end

  defp bfs_distances(source_id, edges) do
    queue = :queue.in({source_id, 0}, :queue.new())
    do_bfs(queue, edges, %{source_id => 0})
  end

  defp do_bfs(queue, edges, distances) do
    case :queue.out(queue) do
      {:empty, _queue} ->
        distances

      {{:value, {node_id, dist}}, rest} ->
        neighbors = Map.get(edges, node_id, [])

        {queue, distances} =
          Enum.reduce(neighbors, {rest, distances}, fn neighbor, {q, d} ->
            if Map.has_key?(d, neighbor) do
              {q, d}
            else
              {:queue.in({neighbor, dist + 1}, q), Map.put(d, neighbor, dist + 1)}
            end
          end)

        do_bfs(queue, edges, distances)
    end
  end
end
