defmodule Tracker.Delivery.User do
  @moduledoc false
  use Ash.Resource,
    otp_app: :tracker,
    domain: Tracker.Delivery,
    data_layer: Ash.DataLayer.Ets,
    extensions: [AshGraphql.Resource]

  ets do
    private? true
  end

  graphql do
    type :user

    hide_fields [:internal_notes]
  end

  attributes do
    uuid_primary_key :id

    attribute :email, :string, allow_nil?: false, public?: true
    attribute :display_name, :string, allow_nil?: false, public?: true

    attribute :role, Tracker.Delivery.UserRole,
      allow_nil?: false,
      default: :member,
      public?: true

    attribute :internal_notes, :string, public?: true
  end

  actions do
    defaults [:read, :destroy, create: :*, update: :*]
  end

  relationships do
    has_many :assigned_tickets, Tracker.Delivery.Ticket do
      destination_attribute :assignee_id
      public? true
    end
  end
end
