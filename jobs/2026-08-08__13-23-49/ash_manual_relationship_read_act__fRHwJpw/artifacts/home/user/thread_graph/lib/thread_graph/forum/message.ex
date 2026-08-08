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
  end
end
