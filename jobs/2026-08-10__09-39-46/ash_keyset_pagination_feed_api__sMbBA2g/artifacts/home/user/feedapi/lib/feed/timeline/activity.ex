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

  aggregates do
    count :reaction_count, :reactions
  end

  calculations do
    calculate :heat, :integer, expr(score * 10 + reaction_count)
  end

  actions do
    defaults [:read, :destroy]

    create :publish do
      accept [:id, :body, :kind, :visibility, :score, :published_at, :author_id]
    end

    update :rescore do
      accept [:score]
    end

    read :feed do
      prepare build(sort: [{:published_at, :desc}, {:id, :asc}])

      pagination do
        keyset? true
        offset? false
        required? true
        default_limit 5
        max_page_size 25
        countable true
      end
    end

    read :feed_offset do
      prepare build(sort: [{:published_at, :desc}, {:id, :asc}])

      pagination do
        keyset? false
        offset? true
        required? true
        default_limit 5
        max_page_size 25
        countable :by_default
      end
    end

    read :public_feed do
      prepare build(sort: [{:published_at, :desc}, {:id, :asc}])

      filter expr(visibility == :public)

      pagination do
        keyset? true
        offset? false
        required? true
        default_limit 4
        max_page_size 25
        countable true
      end
    end

    read :hot_feed do
      prepare build(sort: [{:score, :desc}, {:reaction_count, :desc}, {:id, :asc}])

      pagination do
        keyset? true
        offset? false
        required? true
        default_limit 3
        max_page_size 25
        countable true
      end
    end

    read :heat_feed do
      prepare build(sort: [{:heat, :desc}, {:id, :asc}])

      pagination do
        keyset? true
        offset? false
        required? true
        default_limit 3
        max_page_size 25
        countable true
      end
    end

    read :strict_feed do
      prepare build(sort: [{:published_at, :desc}, {:id, :asc}])

      pagination do
        keyset? true
        offset? false
        required? true
        countable true
      end
    end

    read :uncounted_feed do
      prepare build(sort: [{:published_at, :desc}, {:id, :asc}])

      pagination do
        keyset? true
        offset? false
        required? true
        default_limit 5
        countable false
      end
    end

    read :flexible_feed do
      prepare build(sort: [{:published_at, :desc}, {:id, :asc}])

      pagination do
        keyset? true
        offset? true
        required? false
        default_limit 5
        countable true
      end
    end

    read :author_feed do
      argument :author_id, :string, allow_nil?: false

      prepare build(sort: [{:published_at, :desc}, {:id, :asc}])

      filter expr(author_id == ^arg(:author_id))

      pagination do
        keyset? true
        offset? false
        required? true
        default_limit 5
        max_page_size 10
        countable true
      end
    end
  end
end
