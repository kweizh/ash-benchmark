defmodule Outbox.Eventing do
  @moduledoc """
  The eventing domain: outbox entries, dispatching, and replay.
  """

  use Ash.Domain, otp_app: :outbox

  resources do
    resource Outbox.Eventing.Event
  end

  @doc """
  Returns all stored outbox entries, ascending by sequence.
  """
  def list_events! do
    Outbox.Eventing.Event
    |> Ash.Query.new()
    |> Ash.Query.sort(sequence: :asc)
    |> Ash.read(domain: __MODULE__, authorize?: false)
    |> case do
      {:ok, events} -> events
      {:error, error} -> raise "Failed to list events: #{inspect(error)}"
    end
  end

  @doc """
  Returns outbox entries for one aggregate, ascending by aggregate_sequence.
  """
  def events_for!(aggregate_type, aggregate_id) do
    filter =
      Ash.Filter.parse!(Outbox.Eventing.Event, %{
        "aggregate_type" => aggregate_type,
        "aggregate_id" => aggregate_id
      })

    Outbox.Eventing.Event
    |> Ash.Query.new()
    |> Ash.Query.do_filter(filter)
    |> Ash.Query.sort(aggregate_sequence: :asc)
    |> Ash.read(domain: __MODULE__, authorize?: false)
    |> case do
      {:ok, events} -> events
      {:error, error} -> raise "Failed to list events: #{inspect(error)}"
    end
  end

  @doc """
  Replays all events after the given sequence to the given subscriber.
  Returns `{:ok, delivered_sequences}`.
  """
  def replay(after_sequence, subscriber_id) do
    Outbox.Eventing.Dispatcher.replay(after_sequence, subscriber_id)
  end
end
