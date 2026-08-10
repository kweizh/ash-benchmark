defmodule Feed.Timeline.Reaction do
  @moduledoc """
  A lightweight engagement signal attached to a single activity.
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

    attribute :kind, :atom,
      allow_nil?: false,
      public?: true,
      constraints: [one_of: [:like, :boost]]
  end

  relationships do
    belongs_to :activity, Feed.Timeline.Activity do
      attribute_type :string
      attribute_writable? true
      allow_nil? false
    end
  end

  actions do
    defaults [:read, :destroy]

    create :create do
      accept [:id, :kind, :activity_id]
    end
  end
end
