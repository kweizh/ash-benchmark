defmodule Ingest.Pipeline.Validations.StatusIsNormalized do
  use Ash.Resource.Validation
  import Ash.Expr
  alias Ash.Error.Changes.InvalidAttribute

  @impl true
  def validate(changeset, _opts, _context) do
    if changeset.data.status != :normalized do
      {:error,
       [
         field: :status,
         value: changeset.data.status,
         message: "must equal :normalized"
       ]
       |> InvalidAttribute.exception()}
    else
      :ok
    end
  end

  @impl true
  def atomic(_changeset, _opts, _context) do
    {:atomic, [:status], expr(status != :normalized),
     expr(
       error(^InvalidAttribute, %{
         field: :status,
         value: status,
         message: "must equal :normalized"
       })
     )}
  end
end
