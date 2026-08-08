defmodule OrgGuard.Access.OrgUnit do
  @moduledoc """
  A node in the organisational tree. Documents belong to org units, and role
  grants/denials at an org unit are inherited down the tree via `:parent`.
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
    belongs_to :parent, __MODULE__ do
      public? true
    end

    has_many :children, __MODULE__ do
      destination_attribute :parent_id
      public? true
    end
  end

  actions do
    read :read do
      primary? true
    end

    create :create do
      primary? true
      accept [:code, :name, :parent_id]
    end
  end
end
