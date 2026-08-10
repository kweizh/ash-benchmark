defmodule Vault.Ledger.Event.Validations.VersionSequential do
  @moduledoc """
  Ensures that a new event's `version` is exactly one greater than the
  current highest version in its account's stream.

  Versions that duplicate an already-present version are *not* reported
  here -- that case is instead caught by the `[:account_id, :version]`
  identity, which produces the "has already been taken" error.
  """
  use Ash.Resource.Validation

  require Ash.Query

  @impl true
  def validate(changeset, _opts, _context) do
    account_id = Ash.Changeset.get_attribute(changeset, :account_id)
    version = Ash.Changeset.get_attribute(changeset, :version)

    if is_nil(account_id) or is_nil(version) or not is_integer(version) do
      :ok
    else
      expected = current_version(account_id) + 1

      if version < 1 or version > expected do
        {:error,
         Ash.Error.Changes.InvalidAttribute.exception(
           field: :version,
           message: "version must be exactly one greater than the current stream version",
           vars: [expected: expected]
         )}
      else
        :ok
      end
    end
  end

  defp current_version(account_id) do
    Vault.Ledger.Event
    |> Ash.Query.filter(account_id == ^account_id)
    |> Ash.Query.sort(version: :desc)
    |> Ash.Query.limit(1)
    |> Ash.read_one!(domain: Vault.Ledger, authorize?: false)
    |> case do
      nil -> 0
      event -> event.version
    end
  end
end
