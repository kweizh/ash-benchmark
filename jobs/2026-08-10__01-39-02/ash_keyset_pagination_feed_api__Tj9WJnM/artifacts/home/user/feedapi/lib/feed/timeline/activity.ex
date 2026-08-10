defmodule Feed.Timeline.Activity do
  @moduledoc """
  A single item on the activity feed.

  The write side of this resource is finished. The read side — the feed actions,
  their pagination contracts and the fields they order by — is not.
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
    attribute :body, :string, allow_nil?: false, public?: true

    attribute :kind, :atom,
      allow_nil?: false,
      public?: true,
      constraints: [one_of: [:post, :repost, :reply]]

    attribute :visibility, :atom,
      allow_nil?: false,
      public?: true,
      constraints: [one_of: [:public, :followers]]

    attribute :score, :integer, allow_nil?: false, public?: true, default: 0
    attribute :published_at, :utc_datetime_usec, allow_nil?: false, public?: true
  end

  relationships do
    belongs_to :author, Feed.Timeline.Author do
      attribute_type :string
      attribute_writable? true
      allow_nil? false
    end

    has_many :reactions, Feed.Timeline.Reaction do
      destination_attribute :activity_id
    end
  end

  actions do
    defaults [:read, :destroy]

    create :publish do
      accept [:id, :body, :kind, :visibility, :score, :published_at, :author_id]
    end

    update :rescore do
      accept [:score]
    end
  end
end
