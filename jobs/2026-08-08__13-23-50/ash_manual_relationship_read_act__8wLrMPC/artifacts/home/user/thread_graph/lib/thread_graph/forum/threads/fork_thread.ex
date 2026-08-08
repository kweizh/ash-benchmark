defmodule ThreadGraph.Forum.Threads.ForkThread do
  @moduledoc """
  Implements the `fork` manual create action on `ThreadGraph.Forum.Thread`.

  Copies a source message and every transitive descendant of it (following
  `parent_id`) into a brand new thread, reproducing the parent/child
  structure and renumbering `position` on the copies. A single
  `ThreadGraph.Forum.MessageLink` of kind `:fork_of` is created, linking the
  copy of the source message back to the original source message.
  """
  use Ash.Resource.ManualCreate

  alias ThreadGraph.Forum.LoadCounter
  alias ThreadGraph.Forum.Message
  alias ThreadGraph.Forum.MessageLink
  alias ThreadGraph.Forum.Thread

  @impl true
  def create(changeset, _opts, context) do
    LoadCounter.bump(:fork)

    source_message_id = Ash.Changeset.get_argument(changeset, :source_message_id)
    slug = Ash.Changeset.get_argument(changeset, :slug)
    title = Ash.Changeset.get_argument(changeset, :title)

    read_opts = [
      domain: context.domain || ThreadGraph.Forum,
      actor: context.actor,
      tenant: context.tenant,
      authorize?: context.authorize? || false
    ]

    with {:ok, source} <- fetch_source_message(source_message_id, read_opts),
         {:ok, source_thread} <- fetch_thread(source.thread_id, read_opts),
         :ok <- ensure_not_locked(source_thread) do
      do_fork(source, source_thread, slug, title, read_opts)
    end
  end

  defp fetch_source_message(nil, _read_opts) do
    {:error, invalid_argument("source message not found")}
  end

  defp fetch_source_message(id, read_opts) do
    case Ash.get(Message, id, read_opts) do
      {:ok, nil} -> {:error, invalid_argument("source message not found")}
      {:ok, message} -> {:ok, message}
      {:error, _error} -> {:error, invalid_argument("source message not found")}
    end
  end

  defp fetch_thread(thread_id, read_opts) do
    case Ash.get(Thread, thread_id, read_opts) do
      {:ok, nil} -> {:error, invalid_argument("source message not found")}
      {:ok, thread} -> {:ok, thread}
      {:error, _error} -> {:error, invalid_argument("source message not found")}
    end
  end

  defp ensure_not_locked(%{locked: true}) do
    {:error, invalid_argument("source thread is locked")}
  end

  defp ensure_not_locked(_thread), do: :ok

  defp invalid_argument(message) do
    Ash.Error.Changes.InvalidArgument.exception(field: :source_message_id, message: message)
  end

  defp do_fork(source, source_thread, slug, title, read_opts) do
    with {:ok, all_messages} <- Ash.read(Message, read_opts) do
      children_by_parent = Enum.group_by(all_messages, & &1.parent_id)

      order = topological_order(source, children_by_parent)
      position_map = build_position_map(order)

      with {:ok, new_thread} <-
             Ash.create(
               Thread,
               %{slug: slug, title: title, board: source_thread.board, locked: false},
               read_opts
             ),
           {:ok, id_map} <-
             create_message_copies(order, source, new_thread, position_map, read_opts),
           {:ok, _link} <-
             Ash.create(
               MessageLink,
               %{
                 kind: :fork_of,
                 from_message_id: Map.fetch!(id_map, source.id),
                 to_message_id: source.id
               },
               read_opts
             ) do
        {:ok, new_thread}
      end
    end
  end

  # Breadth-first, parent-before-child order starting at `source`. Guards
  # against cyclic `parent_id` chains via the `visited` set.
  defp topological_order(source, children_by_parent) do
    do_topological_order([source], MapSet.new([source.id]), children_by_parent)
  end

  defp do_topological_order([], _visited, _children_by_parent), do: []

  defp do_topological_order([node | rest], visited, children_by_parent) do
    kids =
      children_by_parent
      |> Map.get(node.id, [])
      |> Enum.reject(&MapSet.member?(visited, &1.id))

    visited = Enum.reduce(kids, visited, &MapSet.put(&2, &1.id))

    [node | do_topological_order(rest ++ kids, visited, children_by_parent)]
  end

  defp build_position_map(order) do
    order
    |> Enum.sort_by(&{&1.position, &1.id})
    |> Enum.with_index(1)
    |> Map.new(fn {message, index} -> {message.id, index} end)
  end

  defp create_message_copies(order, source, new_thread, position_map, read_opts) do
    Enum.reduce_while(order, {:ok, %{}}, fn original, {:ok, id_map} ->
      parent_new_id =
        if original.id == source.id do
          nil
        else
          Map.fetch!(id_map, original.parent_id)
        end

      attrs = %{
        thread_id: new_thread.id,
        body: original.body,
        score: original.score,
        author_id: original.author_id,
        parent_id: parent_new_id,
        position: Map.fetch!(position_map, original.id)
      }

      case Ash.create(Message, attrs, read_opts) do
        {:ok, new_message} -> {:cont, {:ok, Map.put(id_map, original.id, new_message.id)}}
        {:error, error} -> {:halt, {:error, error}}
      end
    end)
  end
end
