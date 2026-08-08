defmodule OrgGuard.Access.Document do
  use Ash.Resource,
    data_layer: Ash.DataLayer.Ets,
    domain: OrgGuard.Access,
    authorizers: [Ash.Policy.Authorizer]

  ets do
    private? false
  end

  attributes do
    uuid_primary_key :id

    attribute :title, :string do
      allow_nil? false
      public? true
    end

    attribute :budget_cents, :integer do
      allow_nil? false
      default 0
      public? true
    end
  end

  relationships do
    belongs_to :org_unit, OrgGuard.Access.OrgUnit do
      allow_nil? false
      public? true
      attribute_writable? true
    end
  end

  actions do
    default_accept :*
    defaults []

    read :read do
      primary? true
    end

    create :create do
      primary? true
      accept [:title, :budget_cents, :org_unit_id]
    end

    update :update do
      primary? true
      accept [:title, :budget_cents]
    end

    destroy :destroy do
      primary? true
    end

    action :relocate, :struct do
      primary? true
      constraints instance_of: OrgGuard.Access.Document

      argument :document_id, :uuid do
        allow_nil? false
      end

      argument :target_org_unit_id, :uuid do
        allow_nil? false
      end

      run fn input, context ->
        document_id = input.arguments.document_id
        target_org_unit_id = input.arguments.target_org_unit_id

        # Fetch the document (bypass authorization since we're inside the action)
        case OrgGuard.Access.Document
             |> Ash.Query.new()
             |> Ash.Query.do_filter(Ash.Filter.parse_input!(OrgGuard.Access.Document, id: document_id))
             |> Ash.read(authorize?: false) do
          {:ok, [document]} ->
            # Update the document's org_unit_id
            document
            |> Ash.Changeset.for_update(:update, %{org_unit_id: target_org_unit_id},
              authorize?: false
            )
            |> Ash.update(authorize?: false)

          {:ok, []} ->
            {:error, "Document not found"}

          {:error, error} ->
            {:error, error}
        end
      end
    end
  end

  policies do
    # Bypass: break_glass actors can do anything (even when suspended)
    bypass actor_attribute_equals(:global_role, :break_glass) do
      authorize_if always()
    end

    # Suspension: any non-break-glass suspended actor is forbidden from everything
    policy actor_attribute_equals(:status, :suspended) do
      forbid_if always()
    end

    # Read policy: uses filter check
    policy action_type(:read) do
      authorize_if {OrgGuard.Access.Checks.HasCapabilityFilter, capability: :read}
    end

    # Create policy: requires write capability at the target org_unit
    policy action_type(:create) do
      authorize_if {OrgGuard.Access.Checks.HasCapabilitySimple, capability: :write}
    end

    # Update policy: requires write capability at the document's org_unit
    policy action_type(:update) do
      authorize_if {OrgGuard.Access.Checks.HasCapabilitySimple, capability: :write}
    end

    # Destroy policy: requires delete capability at the document's org_unit
    policy action_type(:destroy) do
      authorize_if {OrgGuard.Access.Checks.HasCapabilitySimple, capability: :delete}
    end

    # Relocate policy: requires relocate capability at both source and target
    policy action([:relocate]) do
      authorize_if {OrgGuard.Access.Checks.HasCapabilitySimple, capability: :relocate}
    end
  end

  field_policies do
    # budget_cents is only visible to actors with view_budget capability
    # or break_glass actors (handled by the bypass policy)
    field_policy :budget_cents do
      authorize_if {OrgGuard.Access.Checks.HasCapabilitySimple, capability: :view_budget}
    end

    # All other fields are visible to anyone who can read the document
    field_policy :* do
      authorize_if always()
    end
  end

  code_interface do
    define :create, action: :create
    define :read, action: :read
    define :update, action: :update
    define :destroy, action: :destroy
    define :relocate, action: :relocate, args: [:document_id, :target_org_unit_id]
  end
end
