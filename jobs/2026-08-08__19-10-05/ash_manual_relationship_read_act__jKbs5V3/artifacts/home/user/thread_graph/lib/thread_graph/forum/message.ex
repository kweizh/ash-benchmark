defmodule ThreadGraph.Forum.Message do
  @moduledoc "A single message inside a thread."
  use Ash.Resource,
    otp_app: :thread_graph,
    domain: ThreadGraph.Forum,
    data_layer: Ash.DataLayer.Ets

  attributes do
    uuid_primary_key :id

    attribute :body, :string, allow_nil?: false, public?: true
    attribute :position, :integer, allow_nil?: false, public?: true
    attribute :score, :integer, allow_nil?: false, default: 0, public?: true
  end

  actions do
    defaults [
      :read,
      :destroy,
      create: [:body, :position, :score, :thread_id, :author_id, :parent_id],
      update: [:body, :position, :score, :parent_id]
    ]

    read :cross_board_highlights do
      argument :boards, {:array, :string}, allow_nil?: false
      argument :min_endorsements, :integer, default: 0

      manual ThreadGraph.Forum.Messages.CrossBoardHighlights
    end
  end

  aggregates do
    count :reply_count, :replies, public?: true
  end

  relationships do
    belongs_to :thread, ThreadGraph.Forum.Thread do
      allow_nil? false
      attribute_writable? true
      public? true
    end

    belongs_to :author, ThreadGraph.Forum.Author do
      attribute_writable? true
      public? true
    end

    belongs_to :parent, ThreadGraph.Forum.Message do
      source_attribute :parent_id
      attribute_writable? true
      public? true
    end

    has_many :replies, ThreadGraph.Forum.Message do
      destination_attribute :parent_id
      public? true
    end

    has_many :ancestor_messages, ThreadGraph.Forum.Message do
      manual ThreadGraph.Forum.Messages.AncestorMessages
      public? true
    end

    has_many :linked_messages, ThreadGraph.Forum.Message do
      manual ThreadGraph.Forum.Messages.LinkedMessages
      public? true
    end
  end
end
