defmodule OrgGuard.Access.OrgUnit do
  use Ash.Resource,
    data_layer: Ash.DataLayer.Ets,
    domain: OrgGuard.Access

  ets do
    private? false
  end

  attributes do
    uuid_primary_key :id

    attribute :code, :string do
      allow_nil? false
      public? true
    end

    attribute :name, :string do
      allow_nil? false
      public? true
    end
  end

  relationships do
    belongs_to :parent, OrgGuard.Access.OrgUnit do
      public? true
      attribute_writable? true
    end

    has_many :children, OrgGuard.Access.OrgUnit do
      destination_attribute :parent_id
    end
  end

  actions do
    default_accept :*
    defaults [:read, :destroy]

    create :create do
      primary? true
      accept [:code, :name, :parent_id]
    end
  end

  code_interface do
    define :create, action: :create
    define :read, action: :read
  end
end
