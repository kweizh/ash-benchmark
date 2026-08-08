defmodule ThreadGraph.Forum do
  @moduledoc """
  The discussion-board domain.
  """
  use Ash.Domain, otp_app: :thread_graph

  resources do
    resource ThreadGraph.Forum.Author

    resource ThreadGraph.Forum.Thread do
      define :fork_thread, action: :fork, args: [:source_message_id, :slug, :title]
    end

    resource ThreadGraph.Forum.Message do
      define :highlights, action: :cross_board_highlights, args: [:boards, :min_endorsements]
    end

    resource ThreadGraph.Forum.MessageLink
  end
end
