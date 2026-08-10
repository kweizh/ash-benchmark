defmodule Ingest.Pipeline.Validations.UniqueExternalId do
  use Ash.Resource.Validation
  alias Ash.Error.Changes.InvalidAttribute

  @impl true
  def validate(changeset, _opts, _context) do
    external_id = Ash.Changeset.get_attribute(changeset, :external_id)

    if external_id do
      case Ash.get(Ingest.Pipeline.Reading, external_id) do
        {:ok, _} ->
          {:error,
           [
             field: :external_id,
             value: external_id,
             message: "has already been taken"
           ]
           |> InvalidAttribute.exception()}

        {:error, _} ->
          :ok
      end
    else
      :ok
    end
  end
end
