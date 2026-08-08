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
  end
end
