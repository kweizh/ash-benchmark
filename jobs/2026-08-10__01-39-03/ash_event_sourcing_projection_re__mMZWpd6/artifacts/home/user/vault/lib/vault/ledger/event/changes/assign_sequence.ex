defmodule Vault.Ledger.Event.Changes.AssignSequence do
  @moduledoc """
  Assigns the next contiguous global `sequence` to an event immediately
  before it is written, so that a rejected append never consumes a
  sequence number.
  """
  use Ash.Resource.Change

  require Ash.Query

  @impl true
  def change(changeset, _opts, _context) do
    Ash.Changeset.before_action(changeset, fn changeset ->
      Ash.Changeset.force_change_attribute(changeset, :sequence, next_sequence())
    end)
  end

  defp next_sequence do
    Vault.Ledger.Event
    |> Ash.Query.sort(sequence: :desc)
    |> Ash.Query.limit(1)
    |> Ash.read_one!(domain: Vault.Ledger, authorize?: false)
    |> case do
      nil -> 1
      event -> event.sequence + 1
    end
  end
end
