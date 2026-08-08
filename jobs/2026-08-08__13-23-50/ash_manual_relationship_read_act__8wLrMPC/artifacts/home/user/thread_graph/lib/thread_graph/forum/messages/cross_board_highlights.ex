defmodule ThreadGraph.Forum.Messages.CrossBoardHighlights do
  @moduledoc """
  Implements the `cross_board_highlights` manual read action on
  `ThreadGraph.Forum.Message`.

  Returns messages whose thread's `board` is one of the given `boards` and
  whose endorsement count (the number of `ThreadGraph.Forum.MessageLink`
  records of kind `:follow_up` pointing at the message) is at least
  `min_endorsements`. Every returned message carries its endorsement count
  as `:endorsement_count` record metadata.
  """
  use Ash.Resource.ManualRead

  require Ash.Query

  alias ThreadGraph.Forum.LoadCounter
  alias ThreadGraph.Forum.Message
  alias ThreadGraph.Forum.MessageLink
  alias ThreadGraph.Forum.Thread

  @impl true
  def read(ash_query, _data_layer_query, _opts, context) do
    LoadCounter.bump(:cross_board_highlights)

    boards = Ash.Query.get_argument(ash_query, :boards) || []
    min_endorsements = Ash.Query.get_argument(ash_query, :min_endorsements) || 0

    read_opts = [
      domain: context[:domain] || ThreadGraph.Forum,
      actor: context[:actor],
      tenant: context[:tenant],
      authorize?: context[:authorize?] || false
    ]

    with {:ok, threads} <-
           Ash.read(Ash.Query.filter(Thread, board in ^boards), read_opts),
         thread_ids = Enum.map(threads, & &1.id),
         {:ok, links} <-
           Ash.read(Ash.Query.filter(MessageLink, kind == :follow_up), read_opts),
         endorsement_counts = Enum.frequencies_by(links, & &1.to_message_id),
         message_query =
           Message
           |> Ash.Query.filter(thread_id in ^thread_ids)
           |> Ash.Query.do_filter(ash_query.filter),
         {:ok, messages} <- Ash.read(message_query, read_opts) do
      results =
        messages
        |> Enum.map(fn message ->
          count = Map.get(endorsement_counts, message.id, 0)
          Ash.Resource.put_metadata(message, :endorsement_count, count)
        end)
        |> Enum.filter(&(Ash.Resource.get_metadata(&1, :endorsement_count) >= min_endorsements))
        |> sort_messages(ash_query.sort)
        |> apply_offset(ash_query.offset)
        |> apply_limit(ash_query.limit)

      {:ok, results}
    end
  end

  defp sort_messages(messages, sort) when sort in [nil, []] do
    Enum.sort_by(messages, fn message ->
      {-(Ash.Resource.get_metadata(message, :endorsement_count) || 0), message.position,
       message.id}
    end)
  end

  defp sort_messages(messages, sort) do
    Ash.Actions.Sort.runtime_sort(messages, sort, resource: Message)
  end

  defp apply_offset(messages, nil), do: messages
  defp apply_offset(messages, offset), do: Enum.drop(messages, offset)

  defp apply_limit(messages, nil), do: messages
  defp apply_limit(messages, limit), do: Enum.take(messages, limit)
end
