defmodule Outbox.Eventing.Notifier do
  @moduledoc """
  An Ash.Notifier that captures successful writes and stores them in the outbox.
  """

  use Ash.Notifier

  @impl true
  def notify(notification) do
    resource = notification.resource
    action_name = notification.action.name

    # 1. Get aggregate_type
    aggregate_type = Outbox.Eventing.Dispatcher.resource_to_aggregate_type(resource)

    # 2. Topic
    topic = "ledger.#{aggregate_type}.#{action_name}"

    # 3. Get aggregate_id
    aggregate_id = notification.data.id

    # 4. Get actor_id
    actor_id =
      case notification.actor do
        %{id: id} when is_binary(id) -> id
        _ -> nil
      end

    # 5. Get changes
    changes = calculate_changes(notification)

    # 6. Allocate sequence and aggregate_sequence atomically from SequenceServer
    {seq, agg_seq} = Outbox.Eventing.SequenceServer.next_sequences(aggregate_type, aggregate_id)

    # 7. Build dedup_key
    dedup_key = "#{aggregate_type}:#{aggregate_id}:#{action_name}:#{agg_seq}"

    # 8. Create the Event record in Outbox.Eventing domain
    event =
      Outbox.Eventing.Event
      |> Ash.Changeset.for_create(:create, %{
        sequence: seq,
        aggregate_sequence: agg_seq,
        topic: topic,
        resource: String.replace_leading(to_string(resource), "Elixir.", ""),
        aggregate_type: aggregate_type,
        aggregate_id: to_string(aggregate_id),
        action: action_name,
        actor_id: actor_id,
        changes: changes,
        dedup_key: dedup_key
      })
      |> Ash.create!()

    # 9. Notify the Dispatcher of the new event
    Outbox.Eventing.Dispatcher.handle_event(event)

    :ok
  end

  defp calculate_changes(notification) do
    resource = notification.resource
    changeset = notification.changeset
    action_type = notification.action.type

    public_non_pk_attrs =
      resource
      |> Ash.Resource.Info.public_attributes()
      |> Enum.reject(& &1.primary_key?)

    case action_type do
      :create ->
        Enum.reduce(public_non_pk_attrs, %{}, fn attr, acc ->
          val = Map.get(notification.data, attr.name)
          if val != nil do
            Map.put(acc, Atom.to_string(attr.name), %{"from" => nil, "to" => encode_val(val)})
          else
            acc
          end
        end)

      :update ->
        pk_field = :id
        is_single_update =
          is_struct(changeset.data) and
          Map.get(changeset.data, pk_field) == Map.get(notification.data, pk_field) and
          Map.get(changeset.data, pk_field) != nil

        if is_single_update do
          Enum.reduce(public_non_pk_attrs, %{}, fn attr, acc ->
            before_val = Map.get(changeset.data, attr.name)
            after_val = Map.get(notification.data, attr.name)
            if before_val != after_val do
              Map.put(acc, Atom.to_string(attr.name), %{
                "from" => encode_val(before_val),
                "to" => encode_val(after_val)
              })
            else
              acc
            end
          end)
        else
          # Batch update: use keys of changeset.attributes
          Enum.reduce(public_non_pk_attrs, %{}, fn attr, acc ->
            if Map.has_key?(changeset.attributes, attr.name) do
              after_val = Map.get(notification.data, attr.name)
              Map.put(acc, Atom.to_string(attr.name), %{
                "from" => nil,
                "to" => encode_val(after_val)
              })
            else
              acc
            end
          end)
        end

      :destroy ->
        %{}
    end
  end

  defp encode_val(nil), do: nil
  defp encode_val(val) when is_atom(val), do: Atom.to_string(val)
  defp encode_val(val), do: val
end
