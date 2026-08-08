defmodule ThreadGraph.Forum.Messages.CrossBoardHighlights do
  @moduledoc false
  use Ash.Resource.ManualRead

  @impl true
  def read(query, _data_layer_query, _opts, _context) do
    ThreadGraph.Forum.LoadCounter.bump(:cross_board_highlights)

    boards = Ash.Query.get_argument(query, :boards)
    min_endorsements = Ash.Query.get_argument(query, :min_endorsements) || 0

    # Get all messages
    {:ok, all_messages} =
      ThreadGraph.Forum.Message
      |> Ash.Query.load(:thread)
      |> Ash.read(domain: ThreadGraph.Forum)

    # Filter by boards
    board_messages =
      Enum.filter(all_messages, fn msg ->
        msg.thread && msg.thread.board in boards
      end)

    # Get endorsement counts
    message_ids = Enum.map(board_messages, & &1.id)

    endorsement_counts =
      case message_ids do
        [] ->
          %{}

        ids ->
          {:ok, link_filter} =
            Ash.Filter.parse_input(ThreadGraph.Forum.MessageLink, %{
              to_message_id: [in: ids],
              kind: :follow_up
            })

          {:ok, links} =
            ThreadGraph.Forum.MessageLink
            |> Ash.Query.do_filter(link_filter)
            |> Ash.read(domain: ThreadGraph.Forum)

          links
          |> Enum.group_by(& &1.to_message_id)
          |> Map.new(fn {id, links} -> {id, length(links)} end)
      end

    # Filter by min_endorsements and attach metadata
    results =
      board_messages
      |> Enum.filter(fn msg ->
        Map.get(endorsement_counts, msg.id, 0) >= min_endorsements
      end)
      |> Enum.map(fn msg ->
        count = Map.get(endorsement_counts, msg.id, 0)
        Ash.Resource.put_metadata(msg, :endorsement_count, count)
      end)

    # Apply the query's filter if present
    results =
      if query.filter do
        filter_results(query, results)
      else
        results
      end

    # Apply sorting
    results =
      if query.sort && query.sort != [] do
        sort_results(results, query.sort)
      else
        # Default sort: endorsement_count desc, position asc, id asc
        Enum.sort_by(results, fn msg ->
          count = Ash.Resource.get_metadata(msg, :endorsement_count)
          {-count, msg.position, msg.id}
        end)
      end

    # Apply limit and offset
    results =
      if query.offset do
        Enum.drop(results, query.offset)
      else
        results
      end

    results =
      if query.limit do
        Enum.take(results, query.limit)
      else
        results
      end

    {:ok, results}
  end

  defp filter_results(query, results) do
    case Ash.Filter.Runtime.filter_matches(
           query.domain,
           results,
           query.filter,
           tenant: query.tenant,
           actor: query.context[:private][:actor],
           authorize?: query.context[:private][:authorize?],
           tracer: query.context[:private][:tracer]
         ) do
      {:ok, filtered} -> filtered
      _ -> results
    end
  end

  defp sort_results(results, sort) do
    Enum.sort_by(results, fn record ->
      Enum.map(sort, fn {field, direction} ->
        value = Map.get(record, field)
        case direction do
          :asc -> value
          :desc -> {:desc, value}
          :asc_nils_first -> value
          :asc_nils_last -> {:asc_nils_last, value}
          :desc_nils_first -> {:desc_nils_first, value}
          :desc_nils_last -> {:desc_nils_last, value}
        end
      end)
    end)
  end
end
