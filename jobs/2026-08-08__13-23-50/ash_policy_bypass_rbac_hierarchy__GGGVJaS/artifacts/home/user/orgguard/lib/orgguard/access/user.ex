defmodule OrgGuard.Access.User do
  @moduledoc """
  A person who may hold role assignments and act as an actor.
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

    attribute :email, :string do
      allow_nil? false
      public? true
    end

    attribute :status, :atom do
      allow_nil? false
      public? true
      default :active
      constraints one_of: [:active, :suspended]
    end

    attribute :global_role, :atom do
      allow_nil? false
      public? true
      default :member
      constraints one_of: [:member, :break_glass]
    end
  end

  actions do
    read :read do
      primary? true
    end

    create :create do
      primary? true
      accept [:email, :status, :global_role]
    end
  end
end
