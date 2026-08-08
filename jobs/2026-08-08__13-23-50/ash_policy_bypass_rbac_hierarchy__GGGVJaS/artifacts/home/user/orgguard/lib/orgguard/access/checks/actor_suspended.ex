defmodule OrgGuard.Access.Checks.ActorSuspended do
  @moduledoc """
  A simple check that is true when the actor is present and has
  `status: :suspended`.
  """
  use Ash.Policy.SimpleCheck

  @impl true
  def describe(_opts), do: "actor is suspended"

  @impl true
  def match?(nil, _context, _opts), do: false
  def match?(%{status: :suspended}, _context, _opts), do: true
  def match?(_actor, _context, _opts), do: false
end
