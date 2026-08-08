defmodule OrgGuard.Access.User do
  use Ash.Resource,
    data_layer: Ash.DataLayer.Ets,
    domain: OrgGuard.Access

  ets do
    private? false
  end

  attributes do
    uuid_primary_key :id

    attribute :email, :string do
      allow_nil? false
      public? true
    end

    attribute :status, :atom do
      allow_nil? false
      default :active
      constraints one_of: [:active, :suspended]
      public? true
    end

    attribute :global_role, :atom do
      allow_nil? false
      default :member
      constraints one_of: [:member, :break_glass]
      public? true
    end
  end

  actions do
    default_accept :*
    defaults [:read, :destroy]

    create :create do
      primary? true
      accept [:email, :status, :global_role]
    end
  end

  code_interface do
    define :create, action: :create
    define :read, action: :read
  end
end
