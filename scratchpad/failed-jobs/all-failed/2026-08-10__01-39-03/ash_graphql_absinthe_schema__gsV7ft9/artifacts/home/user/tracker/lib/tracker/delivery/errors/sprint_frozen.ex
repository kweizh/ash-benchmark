defmodule Tracker.Delivery.Errors.SprintFrozen do
  @moduledoc false
  use Splode.Error, fields: [:project_slug], class: :invalid

  def message(%{project_slug: slug}) do
    "sprint #{slug} is already frozen"
  end
end

defimpl AshGraphql.Error, for: Tracker.Delivery.Errors.SprintFrozen do
  def to_error(error) do
    %{
      message: "sprint %{project_slug} is already frozen",
      short_message: "sprint frozen",
      code: "sprint_frozen",
      vars: %{project_slug: error.project_slug},
      fields: [:reason]
    }
  end
end
