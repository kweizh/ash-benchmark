defmodule Tracker.Delivery.Project do
  @moduledoc false
  use Ash.Resource,
    otp_app: :tracker,
    domain: Tracker.Delivery,
    data_layer: Ash.DataLayer.Ets,
    authorizers: [Ash.Policy.Authorizer],
    extensions: [AshGraphql.Resource]

  require Ash.Query

  ets do
    private? true
  end

  graphql do
    type :project
  end

  attributes do
    uuid_primary_key :id
    attribute :name, :string, allow_nil?: false, public?: true
    attribute :slug, :string, allow_nil?: false, public?: true
    attribute :archived, :boolean, allow_nil?: false, default: false, public?: true
  end

  actions do
    defaults [:read, :destroy]

    create :create do
      primary? true
      accept [:name, :slug]
    end

    update :archive do
      accept []
      change set_attribute(:archived, true)
    end

    action :audit_sprint, :string do
      allow_nil? true
      argument :slug, :string, allow_nil?: false

      run fn input, _context ->
        raise "audit backend offline for #{input.arguments.slug}"
      end
    end

    action :freeze_sprint, :string do
      argument :slug, :string, allow_nil?: false
      argument :reason, :string, allow_nil?: false

      run fn input, _context ->
        slug = input.arguments.slug

        query = Ash.Query.filter(__MODULE__, slug == ^slug)

        case Ash.read_one(query, authorize?: false) do
          {:ok, nil} ->
            {:error, Ash.Error.Query.NotFound.exception(resource: __MODULE__)}

          {:ok, %{archived: true} = project} ->
            {:error, Tracker.Delivery.Errors.SprintFrozen.exception(project_slug: project.slug)}

          {:ok, project} ->
            {:ok, "frozen:#{project.slug}:#{input.arguments.reason}"}

          {:error, error} ->
            {:error, error}
        end
      end
    end
  end

  policies do
    policy action(:archive) do
      authorize_if actor_attribute_equals(:role, :admin)
    end

    policy always() do
      authorize_if always()
    end
  end

  aggregates do
    count :open_ticket_count, :tickets do
      filter expr(status == :open)
      public? true
    end
  end

  relationships do
    has_many :tickets, Tracker.Delivery.Ticket do
      public? true
    end
  end
end
