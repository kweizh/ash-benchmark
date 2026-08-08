defmodule ThreadGraph.Forum.Author do
  @moduledoc "Somebody who posts messages."
  use Ash.Resource,
    otp_app: :thread_graph,
    domain: ThreadGraph.Forum,
    data_layer: Ash.DataLayer.Ets

  attributes do
    uuid_primary_key :id

    attribute :handle, :string, allow_nil?: false, public?: true
    attribute :display_name, :string, public?: true
  end

  actions do
    defaults [
      :read,
      :destroy,
      create: [:handle, :display_name],
      update: [:handle, :display_name]
    ]
  end

  relationships do
    has_many :messages, ThreadGraph.Forum.Message do
      public? true
    end
  end
end
