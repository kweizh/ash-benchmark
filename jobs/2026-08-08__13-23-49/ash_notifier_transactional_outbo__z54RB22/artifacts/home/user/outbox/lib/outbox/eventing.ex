defmodule Outbox.Eventing do
  @moduledoc """
  The outbox and eventing domain.
  """

  use Ash.Domain, otp_app: :outbox
  require Ash.Query

  resources do
    resource Outbox.Eventing.Event
  end

  def list_events! do
    Outbox.Eventing.Event
    |> Ash.Query.sort(sequence: :asc)
    |> Ash.read!()
  end

  def events_for!(aggregate_type, aggregate_id) do
    Outbox.Eventing.Event
    |> Ash.Query.filter(aggregate_type == ^aggregate_type and aggregate_id == ^aggregate_id)
    |> Ash.Query.sort(aggregate_sequence: :asc)
    |> Ash.read!()
  end

  def replay(after_sequence, subscriber_id) do
    res =
      Outbox.Eventing.Event
      |> Ash.ActionInput.for_action(:replay, %{after_sequence: after_sequence, subscriber_id: subscriber_id})
      |> Ash.run_action!()

    {:ok, res}
  end
end
