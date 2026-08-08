defmodule Outbox.Eventing.Notifier do
  @moduledoc """
  An Ash notifier that captures every successful write to a ledger resource
  as an outbox entry, then hands it to the dispatcher.
  """

  use Ash.Notifier
  require Logger

  @impl true
  def notify(notification) do
    # Only handle ledger resources
    resource = notification.resource

    if ledger_resource?(resource) do
      # Build the topic
      aggregate_type = aggregate_type(resource)
      action_name = notification.action.name
      topic = "ledger.#{aggregate_type}.#{action_name}"

      # Get the record id
      record_id = get_record_id(notification.data)

      # Compute changes diff
      changes = compute_changes(notification, resource)

      # Compute actor_id
      actor_id = compute_actor_id(notification.actor)

      # Atomically get next sequence numbers
      {sequence, aggregate_sequence} =
        Outbox.Eventing.Sequence.next(resource, aggregate_type, record_id)

      dedup_key = "#{aggregate_type}:#{record_id}:#{action_name}:#{aggregate_sequence}"

      # Build and store the event
      event_attrs = %{
        sequence: sequence,
        aggregate_sequence: aggregate_sequence,
        topic: topic,
        resource: resource_string(resource),
        aggregate_type: aggregate_type,
        aggregate_id: record_id,
        action: action_name,
        actor_id: actor_id,
        changes: changes,
        dedup_key: dedup_key
      }

      case Ash.create(Outbox.Eventing.Event, event_attrs,
             domain: Outbox.Eventing,
             authorize?: false
           ) do
        {:ok, event} ->
          # Hand to dispatcher
          Outbox.Eventing.Dispatcher.dispatch(event)

        {:error, error} ->
          # Dedup key collision or other error - log and continue
          Logger.warning(
            "Failed to create outbox event (dedup_key: #{dedup_key}): #{inspect(error)}"
          )
      end
    end

    :ok
  end

  defp ledger_resource?(resource) do
    resource == Outbox.Ledger.Account or resource == Outbox.Ledger.Transfer
  end

  defp aggregate_type(resource) do
    resource
    |> Module.split()
    |> List.last()
    |> Macro.underscore()
  end

  defp resource_string(resource) do
    resource
    |> to_string()
    |> String.replace_prefix("Elixir.", "")
  end

  defp get_record_id(data) when is_struct(data) do
    case Map.get(data, :id) do
      nil -> ""
      id -> to_string(id)
    end
  end

  defp get_record_id(data) when is_map(data) do
    case Map.get(data, :id) do
      nil -> ""
      id -> to_string(id)
    end
  end

  defp compute_actor_id(nil), do: nil

  defp compute_actor_id(actor) when is_map(actor) do
    case Map.get(actor, :id) do
      id when is_binary(id) -> id
      _ -> nil
    end
  end

  defp compute_actor_id(actor) when is_struct(actor) do
    case Map.get(actor, :id) do
      id when is_binary(id) -> id
      _ -> nil
    end
  end

  defp compute_changes(notification, resource) do
    case notification.action.type do
      :create -> changes_for_create(notification, resource)
      :update -> changes_for_update(notification, resource)
      :destroy -> %{}
      _ -> %{}
    end
  end

  defp changes_for_create(notification, resource) do
    data = notification.data
    attrs = Ash.Resource.Info.public_attributes(resource)
    pk_name = Ash.Resource.Info.primary_key(resource)

    Enum.reduce(attrs, %{}, fn attr, acc ->
      # Skip primary key
      if attr.name in List.wrap(pk_name) do
        acc
      else
        value = Map.get(data, attr.name)

        if is_nil(value) do
          acc
        else
          encoded = encode_value(value)
          Map.put(acc, to_string(attr.name), %{"from" => nil, "to" => encoded})
        end
      end
    end)
  end

  defp changes_for_update(notification, resource) do
    changeset = notification.changeset
    data = notification.data
    attrs = Ash.Resource.Info.public_attributes(resource)
    pk_name = Ash.Resource.Info.primary_key(resource)

    # Collect the before values from changeset.data (the original record)
    before_data = if changeset, do: changeset.data, else: nil

    # Collect attribute changes from the changeset
    changed_attrs =
      if changeset do
        # changeset.attributes contains the new values being set
        changeset.attributes
      else
        %{}
      end

    # Also check atomics
    atomics_map =
      if changeset do
        Map.new(changeset.atomics, fn {key, value} -> {key, value} end)
      else
        %{}
      end

    # Merge atomics into changed_attrs (atomics take precedence)
    all_changes = Map.merge(changed_attrs, atomics_map)

    Enum.reduce(attrs, %{}, fn attr, acc ->
      if attr.name in List.wrap(pk_name) do
        acc
      else
        new_value = Map.get(all_changes, attr.name) || Map.get(data, attr.name)
        old_value = if before_data, do: Map.get(before_data, attr.name), else: nil

        # Only include if the value actually changed, or if we can't tell (batch update)
        if before_data == nil or not values_equal?(old_value, new_value) do
          encoded_old = encode_value(old_value)
          encoded_new = encode_value(new_value)
          Map.put(acc, to_string(attr.name), %{"from" => encoded_old, "to" => encoded_new})
        else
          acc
        end
      end
    end)
  end

  defp encode_value(nil), do: nil
  defp encode_value(value) when is_atom(value), do: Atom.to_string(value)
  defp encode_value(value), do: value

  defp values_equal?(nil, nil), do: true
  defp values_equal?(a, b), do: a == b
end
