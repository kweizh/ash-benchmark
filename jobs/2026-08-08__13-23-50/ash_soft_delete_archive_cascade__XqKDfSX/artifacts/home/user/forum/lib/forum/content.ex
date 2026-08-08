defmodule Forum.Content do
  @moduledoc """
  The content domain of the forum.

  Forum resources are registered here.
  """
  use Ash.Domain, otp_app: :forum

  resources do
    resource Forum.Content.Post
    resource Forum.Content.Comment
    resource Forum.Content.Reaction
  end
end
