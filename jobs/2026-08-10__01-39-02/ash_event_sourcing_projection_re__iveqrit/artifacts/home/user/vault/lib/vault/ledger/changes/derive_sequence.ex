defmodule Vault.Ledger.Changes.DeriveSequence do
  use Ash.Resource.Change

  def change(changeset, _opts, _context) do
    Ash.Changeset.before_action(changeset, fn changeset ->
      require Ash.Query
      query = 
        Vault.Ledger.Event
        |> Ash.Query.sort(sequence: :desc)
        |> Ash.Query.limit(1)

      case Ash.read(query) do
        {:ok, [latest_event]} ->
          Ash.Changeset.force_change_attribute(changeset, :sequence, latest_event.sequence + 1)
        {:ok, []} ->
          Ash.Changeset.force_change_attribute(changeset, :sequence, 1)
        _ ->
          changeset
      end
    end)
  end
end
