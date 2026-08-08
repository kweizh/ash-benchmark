defmodule ThreadGraph.Forum.Threads.ForkThread do
  @moduledoc false
  use Ash.Resource.ManualCreate

  @impl true
  def create(changeset, _opts, _context) do
    ThreadGraph.Forum.LoadCounter.bump(:fork)

    source_message_id = Ash.Changeset.get_argument(changeset, :source_message_id)
    slug = Ash.Changeset.get_argument(changeset, :slug)
    title = Ash.Changeset.get_argument(changeset, :title)

    # Find the source message
    {:ok, msg_filter} =
      Ash.Filter.parse_input(ThreadGraph.Forum.Message, %{id: source_message_id})

    {:ok, source_messages} =
      ThreadGraph.Forum.Message
      |> Ash.Query.do_filter(msg_filter)
      |> Ash.Query.load(:thread)
      |> Ash.read(domain: ThreadGraph.Forum)

    source_message = List.first(source_messages)

    # Check failure modes
    if source_message == nil do
      {:error,
       Ash.Error.to_error_class([
         %Ash.Error.Changes.InvalidArgument{
           field: :source_message_id,
           message: "source message not found",
           value: source_message_id
         }
       ])}
    else
      if source_message.thread.locked do
        {:error,
         Ash.Error.to_error_class([
           %Ash.Error.Changes.InvalidArgument{
             field: :source_message_id,
             message: "source thread is locked",
             value: source_message_id
           }
         ])}
      else
        do_fork(source_message, slug, title)
      end
    end
  end

  defp do_fork(source_message, slug, title) do
    # Step 1: Fetch all descendants of S
    {:ok, thread_filter} =
      Ash.Filter.parse_input(ThreadGraph.Forum.Message, %{thread_id: source_message.thread_id})

    {:ok, all_thread_messages} =
      ThreadGraph.Forum.Message
      |> Ash.Query.do_filter(thread_filter)
      |> Ash.read(domain: ThreadGraph.Forum)

    all_by_id = Map.new(all_thread_messages, &{&1.id, &1})

    # Collect S and all transitive descendants
    {descendant_ids, _} =
      collect_descendants(source_message.id, all_by_id, MapSet.new([source_message.id]))

    descendants =
      descendant_ids
      |> MapSet.to_list()
      |> Enum.map(&Map.get(all_by_id, &1))
      |> Enum.sort_by(&{&1.position, &1.id})

    # Step 2: Create the new thread
    {:ok, new_thread} =
      ThreadGraph.Forum.Thread
      |> Ash.Changeset.for_create(:create, %{
        slug: slug,
        title: title,
        board: source_message.thread.board,
        locked: false
      })
      |> Ash.create(domain: ThreadGraph.Forum)

    # Step 3: Copy messages to the new thread
    id_mapping = %{}

    {_created_messages, id_mapping} =
      Enum.reduce(descendants, {[], id_mapping}, fn original, {messages, mapping} ->
        new_parent_id =
          case original.parent_id do
            nil -> nil
            pid -> Map.get(mapping, pid)
          end

        {:ok, new_msg} =
          ThreadGraph.Forum.Message
          |> Ash.Changeset.for_create(:create, %{
            body: original.body,
            position: length(messages) + 1,
            score: original.score,
            thread_id: new_thread.id,
            author_id: original.author_id,
            parent_id: new_parent_id
          })
          |> Ash.create(domain: ThreadGraph.Forum)

        {messages ++ [new_msg], Map.put(mapping, original.id, new_msg.id)}
      end)

    # Step 4: Create the fork_of MessageLink
    copy_of_s_id = Map.get(id_mapping, source_message.id)

    {:ok, _link} =
      ThreadGraph.Forum.MessageLink
      |> Ash.Changeset.for_create(:create, %{
        kind: :fork_of,
        from_message_id: copy_of_s_id,
        to_message_id: source_message.id
      })
      |> Ash.create(domain: ThreadGraph.Forum)

    {:ok, new_thread}
  end

  defp collect_descendants(parent_id, all_by_id, visited) do
    children =
      all_by_id
      |> Enum.filter(fn {_id, msg} -> msg.parent_id == parent_id end)
      |> Enum.map(fn {id, _msg} -> id end)
      |> Enum.reject(fn id -> MapSet.member?(visited, id) end)

    {visited, _} =
      Enum.reduce(children, {visited, visited}, fn child_id, {vis, _} ->
        {new_vis, _} = collect_descendants(child_id, all_by_id, MapSet.put(vis, child_id))
        {new_vis, new_vis}
      end)

    {MapSet.put(visited, parent_id), visited}
  end
end
