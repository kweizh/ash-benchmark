defmodule ThreadGraph.Forum.Thread do
  @moduledoc "A discussion thread on a board."
  use Ash.Resource,
    otp_app: :thread_graph,
    domain: ThreadGraph.Forum,
    data_layer: Ash.DataLayer.Ets

  attributes do
    uuid_primary_key :id

    attribute :slug, :string, allow_nil?: false, public?: true
    attribute :title, :string, allow_nil?: false, public?: true
    attribute :board, :string, allow_nil?: false, public?: true
    attribute :locked, :boolean, allow_nil?: false, default: false, public?: true
  end

  actions do
    defaults [
      :read,
      :destroy,
      create: [:slug, :title, :board, :locked],
      update: [:title, :locked]
    ]
  end

  relationships do
    has_many :messages, ThreadGraph.Forum.Message do
      public? true
    end
  end
end
