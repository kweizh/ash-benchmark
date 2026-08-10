defmodule Vault.Ledger.Validations.VersionSequence do
  use Ash.Resource.Validation

  def validate(changeset, _opts, _context) do
    account_id = Ash.Changeset.get_attribute(changeset, :account_id)
    version = Ash.Changeset.get_attribute(changeset, :version)

    if account_id == nil or version == nil do
      :ok
    else
      require Ash.Query
      query = 
        Vault.Ledger.Event
        |> Ash.Query.filter(account_id == ^account_id)
        |> Ash.Query.sort(version: :desc)
        |> Ash.Query.limit(1)

      case Ash.read(query) do
        {:ok, [latest_event]} ->
          expected_version = latest_event.version + 1
          if version == expected_version do
            :ok
          else
            if version >= 1 and version <= latest_event.version do
              {:error, Ash.Error.Changes.InvalidChanges.exception(fields: [:account_id, :version], message: "has already been taken")}
            else
              {:error, Ash.Error.Changes.InvalidAttribute.exception(
                field: :version,
                message: "version must be exactly one greater than the current stream version",
                vars: [expected: expected_version]
              )}
            end
          end

        {:ok, []} ->
          if version == 1 do
            :ok
          else
            {:error, Ash.Error.Changes.InvalidAttribute.exception(
              field: :version,
              message: "version must be exactly one greater than the current stream version",
              vars: [expected: 1]
            )}
          end

        _ ->
          :ok
      end
    end
  end
end
