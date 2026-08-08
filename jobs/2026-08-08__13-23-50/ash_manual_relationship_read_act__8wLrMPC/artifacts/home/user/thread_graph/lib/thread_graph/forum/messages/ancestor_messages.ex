defmodule ThreadGraph.Forum.Messages.AncestorMessages do
  @moduledoc """
  Implements the `ancestor_messages` manual relationship on
  `ThreadGraph.Forum.Message`.

  For each source message (independently of the others), the value is the
  transitive chain of parents reached by repeatedly following `parent_id`,
  ordered outermost ancestor first, immediate parent last. The source
  message itself is never included, no message appears twice, and
  traversal terminates on a cyclic `parent_id` chain.
  """
  use Ash.Resource.ManualRelationship

  alias ThreadGraph.Forum.LoadCounter
  alias ThreadGraph.Forum.Message

  @impl true
  def load(sources, _opts, context) do
    LoadCounter.bump(:ancestor_messages)

    read_opts = [
      domain: context.domain || ThreadGraph.Forum,
      actor: context.actor,
      tenant: context.tenant,
      authorize?: context.authorize? || false
    ]

    with {:ok, all_messages} <- Ash.read(Message, read_opts) do
      by_id = Map.new(all_messages, &{&1.id, &1})

      result = Map.new(sources, fn source -> {source.id, ancestors_of(source, by_id)} end)

      {:ok, result}
    end
  end

  defp ancestors_of(source, by_id) do
    collect(source.parent_id, by_id, MapSet.new([source.id]), [])
  end

  defp collect(nil, _by_id, _visited, acc), do: acc

  defp collect(next_id, by_id, visited, acc) do
    if MapSet.member?(visited, next_id) do
      acc
    else
      case Map.fetch(by_id, next_id) do
        {:ok, message} ->
          collect(message.parent_id, by_id, MapSet.put(visited, next_id), [message | acc])

        :error ->
          acc
      end
    end
  end
end
