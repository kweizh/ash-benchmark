defmodule ThreadGraph.Forum.Threads.RecentMessages do
  @moduledoc """
  Implements the `recent_messages` manual relationship on
  `ThreadGraph.Forum.Thread`.

  For each source thread (independently of the others), the value is that
  thread's own messages ordered by `position` descending (ties broken by
  `id` ascending), truncated to at most 3. A filter present on the load
  query is applied to the candidate messages before the truncation. The
  ordering and the cap of 3 are not affected by any sort or limit present
  on the load query.
  """
  use Ash.Resource.ManualRelationship

  require Ash.Query

  alias ThreadGraph.Forum.LoadCounter
  alias ThreadGraph.Forum.Message

  @max_recent 3

  @impl true
  def load(threads, _opts, context) do
    LoadCounter.bump(:recent_messages)

    thread_ids = Enum.map(threads, & &1.id)

    read_opts = [
      domain: context.domain || ThreadGraph.Forum,
      actor: context.actor,
      tenant: context.tenant,
      authorize?: context.authorize? || false
    ]

    query =
      Message
      |> Ash.Query.filter(thread_id in ^thread_ids)
      |> Ash.Query.do_filter(context.query.filter)

    with {:ok, messages} <- Ash.read(query, read_opts) do
      grouped =
        messages
        |> Enum.group_by(& &1.thread_id)
        |> Map.new(fn {thread_id, msgs} ->
          {thread_id,
           msgs
           |> Enum.sort_by(&{-&1.position, &1.id})
           |> Enum.take(@max_recent)}
        end)

      result = Map.new(threads, fn thread -> {thread.id, Map.get(grouped, thread.id, [])} end)

      {:ok, result}
    end
  end
end
