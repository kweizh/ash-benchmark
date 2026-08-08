defmodule Outbox.Eventing.Event do
  @moduledoc """
  An outbox event entry.
  """

  use Ash.Resource,
    otp_app: :outbox,
    domain: Outbox.Eventing,
    data_layer: Ash.DataLayer.Ets

  require Ash.Query

  ets do
    private? false
  end

  attributes do
    uuid_primary_key :id

    attribute :sequence, :integer, allow_nil?: false, public?: true
    attribute :aggregate_sequence, :integer, allow_nil?: false, public?: true
    attribute :topic, :string, allow_nil?: false, public?: true
    attribute :resource, :string, allow_nil?: false, public?: true
    attribute :aggregate_type, :string, allow_nil?: false, public?: true
    attribute :aggregate_id, :string, allow_nil?: false, public?: true
    attribute :action, :atom, allow_nil?: false, public?: true
    attribute :actor_id, :string, allow_nil?: true, public?: true
    attribute :changes, :map, allow_nil?: false, public?: true
    attribute :dedup_key, :string, allow_nil?: false, public?: true
  end

  identities do
    identity :unique_dedup_key, [:dedup_key], pre_check_with: Outbox.Eventing
  end

  actions do
    defaults [:read, :destroy]

    create :create do
      primary? true
      accept [
        :sequence,
        :aggregate_sequence,
        :topic,
        :resource,
        :aggregate_type,
        :aggregate_id,
        :action,
        :actor_id,
        :changes,
        :dedup_key
      ]
    end

    action :replay, {:array, :integer} do
      argument :after_sequence, :integer, allow_nil?: false
      argument :subscriber_id, :atom, allow_nil?: false

      run fn input, _context ->
        after_seq = input.arguments.after_sequence
        sub_id = input.arguments.subscriber_id

        case Outbox.Eventing.Dispatcher.get_subscriber(sub_id) do
          nil ->
            {:ok, []}

          sub ->
            events =
              Outbox.Eventing.Event
              |> Ash.Query.filter(sequence > ^after_seq)
              |> Ash.Query.sort(sequence: :asc)
              |> Ash.read!()

            delivered =
              Enum.reduce(events, [], fn event, acc ->
                if Outbox.Eventing.Dispatcher.match_topic?(sub.pattern, event.topic) do
                  res =
                    try do
                      sub.handler.(event)
                    rescue
                      _ -> :error
                    catch
                      _, _ -> :error
                    end

                  if res == :ok do
                    [event.sequence | acc]
                  else
                    acc
                  end
                else
                  acc
                end
              end)

            {:ok, Enum.reverse(delivered)}
        end
      end
    end
  end
end
