defmodule Orchestra.Fleet.Rollout do
  use Ash.Resource,
    domain: Orchestra.Fleet,
    data_layer: Ash.DataLayer.Ets

  attributes do
    uuid_primary_key :id
    attribute :name, :string, allow_nil?: false
    attribute :strategy, :atom, allow_nil?: false, constraints: [one_of: [:canary, :blast]]
    attribute :status, :atom, default: :pending, allow_nil?: false, constraints: [one_of: [:pending, :running, :succeeded, :rolled_back]]
    attribute :deployed_node_count, :integer, default: 0, allow_nil?: false
  end

  actions do
    defaults [:read, :destroy]

    create :create do
      accept [:name, :strategy, :status, :deployed_node_count]
      primary? true
    end

    update :update do
      accept [:name, :strategy, :status, :deployed_node_count]
      primary? true
    end

    update :rollback do
      argument :changeset, :term
      change set_attribute(:status, :rolled_back)
      change set_attribute(:deployed_node_count, 0)
    end

    action :plan_rollout, :map do
      argument :targets, {:array, :map}, allow_nil?: false

      run fn input, _ ->
        targets = input.arguments.targets
        cond do
          Enum.empty?(targets) ->
            invalid_argument_error(targets, "targets cannot be empty")

          Enum.any?(targets, fn t ->
            slots = Map.get(t, :slots) || Map.get(t, "slots")
            is_nil(slots) or !is_integer(slots) or slots <= 0
          end) ->
            invalid_argument_error(targets, "all targets must have a positive integer slots")

          true ->
            node_names = Enum.map(targets, fn t -> Map.get(t, :node_name) || Map.get(t, "node_name") end)
            if length(node_names) != length(Enum.uniq(node_names)) do
              invalid_argument_error(targets, "node names must be unique")
            else
              total_slots = Enum.reduce(targets, 0, fn t, acc ->
                slots = Map.get(t, :slots) || Map.get(t, "slots")
                acc + slots
              end)
              sorted_names = Enum.sort(node_names)
              {:ok, %{total_slots: total_slots, node_names: sorted_names, target_count: length(targets)}}
            end
        end
      end
    end
  end

  defp invalid_argument_error(targets, message) do
    err = %Ash.Error.Action.InvalidArgument{
      field: :targets,
      message: message,
      value: targets
    }
    {:error, Ash.Error.to_error_class(err)}
  end
end
