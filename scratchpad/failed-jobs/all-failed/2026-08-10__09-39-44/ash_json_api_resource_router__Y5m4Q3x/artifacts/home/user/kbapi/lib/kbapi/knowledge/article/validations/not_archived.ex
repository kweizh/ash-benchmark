defmodule Kbapi.Knowledge.Article.Validations.NotArchived do
  @moduledoc false
  use Ash.Resource.Validation

  @impl true
  def validate(changeset, _opts, _context) do
    if changeset.data.status == :archived do
      {:error,
       Ash.Error.Changes.InvalidAttribute.exception(
         field: :status,
         message: "cannot publish an archived article"
       )}
    else
      :ok
    end
  end
end
