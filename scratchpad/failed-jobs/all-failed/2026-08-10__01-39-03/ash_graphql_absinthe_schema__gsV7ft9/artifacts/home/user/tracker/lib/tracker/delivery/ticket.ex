defmodule Tracker.Delivery.Ticket do
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
    type :ticket

    field_names estimate_points: :points

    hide_fields [:internal_reference]

    argument_names create: [labels: :new_labels]

    managed_relationships do
      managed_relationship :create, :labels do
        type_name :ticket_label_input
      end
    end
  end

  attributes do
    uuid_primary_key :id

    attribute :title, :string, allow_nil?: false, public?: true

    attribute :status, Tracker.Delivery.TicketStatus,
      allow_nil?: false,
      default: :open,
      public?: true

    attribute :severity, :integer, allow_nil?: false, default: 1, public?: true
    attribute :estimate_points, :integer, allow_nil?: false, default: 0, public?: true
    attribute :sequence, :integer, allow_nil?: false, default: 0, public?: true
    attribute :internal_reference, :string, public?: true
  end

  actions do
    defaults [:destroy]

    read :read do
      primary? true
      pagination keyset?: true, offset?: true, required?: false
    end

    read :top_severity do
      prepare build(sort: [severity: :desc, sequence: :asc], limit: 1)
    end

    create :create do
      primary? true

      accept [
        :title,
        :status,
        :severity,
        :estimate_points,
        :sequence,
        :internal_reference,
        :project_id,
        :assignee_id
      ]

      argument :labels, {:array, :map}

      change manage_relationship(:labels, type: :create)

      validate string_length(:title, min: 3), message: "must be at least 3 characters"
    end

    update :update do
      primary? true
      require_atomic? false
      accept [:title, :status, :severity, :estimate_points, :assignee_id]

      validate string_length(:title, min: 3), message: "must be at least 3 characters"
    end
  end

  calculations do
    calculate :risk_score, :integer, expr(severity * ^arg(:weight) + estimate_points) do
      public? true

      argument :weight, :integer do
        allow_nil? false
      end
    end
  end

  relationships do
    belongs_to :project, Tracker.Delivery.Project do
      allow_nil? false
      attribute_writable? true
      public? true
    end

    belongs_to :assignee, Tracker.Delivery.User do
      attribute_writable? true
      public? true
    end

    many_to_many :labels, Tracker.Delivery.Label do
      through Tracker.Delivery.TicketLabel
      source_attribute_on_join_resource :ticket_id
      destination_attribute_on_join_resource :label_id
      public? true
    end
  end
end
