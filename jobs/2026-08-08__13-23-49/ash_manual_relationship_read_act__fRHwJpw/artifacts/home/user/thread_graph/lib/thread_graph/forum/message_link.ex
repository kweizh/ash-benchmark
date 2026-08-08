defmodule ThreadGraph.Forum.MessageLink do
  @moduledoc "A directed edge between two messages."
  use Ash.Resource,
    otp_app: :thread_graph,
    domain: ThreadGraph.Forum,
    data_layer: Ash.DataLayer.Ets

  attributes do
    uuid_primary_key :id

    attribute :kind, :atom,
      allow_nil?: false,
      public?: true,
      constraints: [one_of: [:follow_up, :duplicate_of, :fork_of]]
  end

  actions do
    defaults [
      :read,
      :destroy,
      create: [:kind, :from_message_id, :to_message_id]
    ]
  end

  relationships do
    belongs_to :from_message, ThreadGraph.Forum.Message do
      allow_nil? false
      attribute_writable? true
      public? true
    end

    belongs_to :to_message, ThreadGraph.Forum.Message do
      allow_nil? false
      attribute_writable? true
      public? true
    end
  end
end
