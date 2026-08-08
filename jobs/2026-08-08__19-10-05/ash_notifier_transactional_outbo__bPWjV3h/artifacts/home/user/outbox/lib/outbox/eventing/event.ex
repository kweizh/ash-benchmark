defmodule Outbox.Eventing.Event do
  @moduledoc """
  An outbox event recording a successful write to a ledger resource.
  """

  use Ash.Resource,
    otp_app: :outbox,
    domain: Outbox.Eventing,
    data_layer: Ash.DataLayer.Ets

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
    attribute :changes, :map, allow_nil?: false, default: %{}, public?: true
    attribute :dedup_key, :string, allow_nil?: false, public?: true
  end

  identities do
    identity :unique_dedup_key, [:dedup_key], pre_check_with: Outbox.Eventing
  end

  actions do
    defaults [:read]

    create :create_event do
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
        Outbox.Eventing.replay(input.arguments.after_sequence, input.arguments.subscriber_id)
      end
    end
  end
end
