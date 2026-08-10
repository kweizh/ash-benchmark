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

      define :feed, action: :feed
      define :feed_offset, action: :feed_offset
      define :public_feed, action: :public_feed
      define :hot_feed, action: :hot_feed
      define :heat_feed, action: :heat_feed
      define :strict_feed, action: :strict_feed
      define :uncounted_feed, action: :uncounted_feed
      define :flexible_feed, action: :flexible_feed
      define :author_feed, action: :author_feed, args: [:author_id]
    end
  end
end
