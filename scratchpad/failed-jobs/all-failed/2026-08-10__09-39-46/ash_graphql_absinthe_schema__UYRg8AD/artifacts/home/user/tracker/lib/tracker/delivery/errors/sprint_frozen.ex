defmodule Tracker.Delivery.Errors.SprintFrozen do
  @moduledoc false
  use Splode.Error, fields: [:project_slug], class: :invalid

  def message(%{project_slug: slug}) do
    "sprint #{slug} is already frozen"
  end
end
