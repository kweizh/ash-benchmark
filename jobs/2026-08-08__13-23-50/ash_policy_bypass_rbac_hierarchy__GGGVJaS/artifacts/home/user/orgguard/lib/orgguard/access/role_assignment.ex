defmodule OrgGuard.Access.RoleAssignment do
  @moduledoc """
  Grants (or revokes) a role for a user at a particular org unit.
  """
  use Ash.Resource,
    otp_app: :orgguard,
    domain: OrgGuard.Access,
    data_layer: Ash.DataLayer.Ets

  ets do
    private? false
  end

  attributes do
    uuid_primary_key :id

    attribute :role, :atom do
      allow_nil? false
      public? true
      constraints one_of: [:viewer, :editor, :auditor, :unit_admin]
    end

    attribute :effect, :atom do
      allow_nil? false
      public? true
      default :grant
      constraints one_of: [:grant, :deny]
    end
  end

  relationships do
    belongs_to :user, OrgGuard.Access.User do
      allow_nil? false
      public? true
    end

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
      accept [:user_id, :org_unit_id, :role, :effect]
    end
  end
end
