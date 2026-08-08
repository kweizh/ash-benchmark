defmodule OrgGuard.Access.RoleAssignment do
  use Ash.Resource,
    data_layer: Ash.DataLayer.Ets,
    domain: OrgGuard.Access

  ets do
    private? false
  end

  attributes do
    uuid_primary_key :id

    attribute :role, :atom do
      allow_nil? false
      constraints one_of: [:viewer, :editor, :auditor, :unit_admin]
      public? true
    end

    attribute :effect, :atom do
      allow_nil? false
      default :grant
      constraints one_of: [:grant, :deny]
      public? true
    end
  end

  relationships do
    belongs_to :user, OrgGuard.Access.User do
      allow_nil? false
      public? true
      attribute_writable? true
    end

    belongs_to :org_unit, OrgGuard.Access.OrgUnit do
      allow_nil? false
      public? true
      attribute_writable? true
    end
  end

  actions do
    default_accept :*
    defaults [:read, :destroy]

    create :create do
      primary? true
      accept [:user_id, :org_unit_id, :role, :effect]
    end
  end

  code_interface do
    define :create, action: :create
    define :read, action: :read
  end
end
