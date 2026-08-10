defmodule Feed.Timeline do
  @moduledoc """
  The activity feed domain.

  Only the write-side code interfaces are wired up so far.
  """

  use Ash.Domain, otp_app: :feedapi

  resources do
    resource Feed.Timeline.Author do
      define :create_author, action: :create
    end

    resource Feed.Timeline.Reaction do
      define :create_reaction, action: :create
    end

    resource Feed.Timeline.Activity do
      define :publish_activity, action: :publish
      define :rescore_activity, action: :rescore
      define :destroy_activity, action: :destroy
    end
  end
end
