defmodule OrgGuard.Access.Document do
  @moduledoc """
  A document belonging to an org unit. Access is governed entirely by
  `Ash.Policy.Authorizer`, using the hierarchical role-based capability
  resolution implemented in `OrgGuard.Access.Capabilities`.
  """
  use Ash.Resource,
    otp_app: :orgguard,
    domain: OrgGuard.Access,
    data_layer: Ash.DataLayer.Ets,
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
      public? true
      default 0
    end
  end

  relationships do
    belongs_to :org_unit, OrgGuard.Access.OrgUnit do
      allow_nil? false
      public? true
    end
  end

  actions do
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
      constraints instance_of: __MODULE__

      argument :document_id, :uuid, allow_nil?: false
      argument :target_org_unit_id, :uuid, allow_nil?: false

      run fn input, _context ->
        document_id = input.arguments.document_id
        target_org_unit_id = input.arguments.target_org_unit_id

        case Ash.get(__MODULE__, document_id, authorize?: false) do
          {:ok, document} ->
            document
            |> Ash.Changeset.for_update(:update, %{}, authorize?: false)
            |> Ash.Changeset.force_change_attribute(:org_unit_id, target_org_unit_id)
            |> Ash.update(authorize?: false)

          {:error, error} ->
            {:error, error}
        end
      end
    end
  end

  policies do
    # Break-glass: security staff with `global_role: :break_glass` may do
    # anything to any document, regardless of role assignments and even
    # while their own account is suspended.
    bypass actor_attribute_equals(:global_role, :break_glass) do
      authorize_if always()
    end

    # Suspended accounts are locked out of every document operation.
    policy always() do
      forbid_if OrgGuard.Access.Checks.ActorSuspended
      authorize_if always()
    end

    policy action_type(:read) do
      authorize_if OrgGuard.Access.Checks.CanReadOrgUnit
    end

    policy action_type(:create) do
      authorize_if OrgGuard.Access.Checks.CanCreateDocument
    end

    policy action_type(:update) do
      authorize_if OrgGuard.Access.Checks.CanUpdateDocument
    end

    policy action_type(:destroy) do
      authorize_if OrgGuard.Access.Checks.CanDestroyDocument
    end

    policy action(:relocate) do
      authorize_if OrgGuard.Access.Checks.CanRelocateDocument
    end
  end

  field_policies do
    field_policy :budget_cents do
      authorize_if actor_attribute_equals(:global_role, :break_glass)
      authorize_if OrgGuard.Access.Checks.CanViewBudget
    end

    field_policy :* do
      authorize_if always()
    end
  end
end
