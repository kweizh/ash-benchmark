defmodule OrgGuard.Access do
  @moduledoc """
  The OrgGuard access-control domain.

  Register the User, OrgUnit, RoleAssignment and Document resources here, together
  with the code interface described in the task.
  """
  use Ash.Domain, otp_app: :orgguard

  resources do
    resource OrgGuard.Access.User do
      define :create_user, action: :create
      define :get_user, action: :read, get_by: [:id]
    end

    resource OrgGuard.Access.OrgUnit do
      define :create_org_unit, action: :create
      define :get_org_unit, action: :read, get_by: [:id]
    end

    resource OrgGuard.Access.RoleAssignment do
      define :create_role_assignment, action: :create
      define :list_role_assignments, action: :read
    end

    resource OrgGuard.Access.Document do
      define :create_document, action: :create
      define :list_documents, action: :read
      define :get_document, action: :read, get_by: [:id]
      define :update_document, action: :update
      define :destroy_document, action: :destroy
      define :relocate_document, action: :relocate, args: [:document_id, :target_org_unit_id]
    end
  end
end
