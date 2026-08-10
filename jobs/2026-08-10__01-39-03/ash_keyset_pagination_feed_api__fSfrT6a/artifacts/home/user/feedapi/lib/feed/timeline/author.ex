defmodule Feed.Timeline.Author do
  @moduledoc """
  A person who publishes activities onto the feed.
  """

  use Ash.Resource,
    otp_app: :feedapi,
    domain: Feed.Timeline,
    data_layer: Ash.DataLayer.Ets

  ets do
    private? true
  end

  attributes do
    attribute :id, :string, primary_key?: true, allow_nil?: false, public?: true, writable?: true
    attribute :handle, :string, allow_nil?: false, public?: true
  end

  relationships do
    has_many :activities, Feed.Timeline.Activity do
      destination_attribute :author_id
    end
  end

  actions do
    defaults [:read, :destroy]

    create :create do
      accept [:id, :handle]
    end
  end
end
