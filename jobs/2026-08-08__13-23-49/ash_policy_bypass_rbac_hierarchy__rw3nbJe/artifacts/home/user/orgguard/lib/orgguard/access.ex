defmodule OrgGuard.Access do
  @moduledoc """
  The OrgGuard access-control domain.

  Register the User, OrgUnit, RoleAssignment and Document resources here, together
  with the code interface described in the task.
  """
  use Ash.Domain, otp_app: :orgguard

  resources do
  end
end
