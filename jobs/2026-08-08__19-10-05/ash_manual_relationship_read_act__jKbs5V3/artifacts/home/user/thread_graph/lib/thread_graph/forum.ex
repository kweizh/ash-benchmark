defmodule ThreadGraph.Forum do
  @moduledoc """
  The discussion-board domain.
  """
  use Ash.Domain, otp_app: :thread_graph

  resources do
    resource ThreadGraph.Forum.Author
    resource ThreadGraph.Forum.Thread
    resource ThreadGraph.Forum.Message
    resource ThreadGraph.Forum.MessageLink

    resource ThreadGraph.Forum.Message do
      define :highlights, action: :cross_board_highlights, args: [:boards, {:optional, :min_endorsements}]
    end

    resource ThreadGraph.Forum.Thread do
      define :fork_thread, action: :fork, args: [:source_message_id, :slug, :title]
    end
  end
end
