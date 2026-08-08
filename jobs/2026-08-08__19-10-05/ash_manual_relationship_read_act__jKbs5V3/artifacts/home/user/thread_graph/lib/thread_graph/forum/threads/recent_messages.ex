defmodule ThreadGraph.Forum.Threads.RecentMessages do
  @moduledoc false
  use Ash.Resource.ManualRelationship

  @impl true
  def load(threads, _opts, context) do
    ThreadGraph.Forum.LoadCounter.bump(:recent_messages)

    thread_ids = Enum.map(threads, & &1.id)

    # Build the base filter using Ash.Filter.parse_input
    {:ok, base_filter} =
      Ash.Filter.parse_input(ThreadGraph.Forum.Message, %{thread_id: [in: thread_ids]})

    # Apply the load query's filter if present
    filter =
      case context.query.filter do
        nil ->
          base_filter

        f ->
          case Ash.Filter.add_to_filter(base_filter, f, :and) do
            {:ok, combined} -> combined
            _ -> base_filter
          end
      end

    query =
      ThreadGraph.Forum.Message
      |> Ash.Query.do_filter(filter)
      |> Ash.Query.sort(position: :desc, id: :asc)

    {:ok, all_messages} = Ash.read(query, domain: ThreadGraph.Forum)

    grouped =
      Enum.group_by(all_messages, & &1.thread_id)
      |> Map.new(fn {thread_id, msgs} ->
        {thread_id, Enum.take(msgs, 3)}
      end)

    result =
      Enum.map(threads, fn thread ->
        Map.get(grouped, thread.id, [])
      end)

    {:ok, result}
  end
end
