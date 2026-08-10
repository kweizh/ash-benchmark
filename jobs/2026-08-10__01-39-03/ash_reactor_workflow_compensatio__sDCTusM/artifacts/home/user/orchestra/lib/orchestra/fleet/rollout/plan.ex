defmodule Orchestra.Fleet.Rollout.Plan do
  @moduledoc """
  Implements the validation/aggregation logic for the `Orchestra.Fleet.Rollout`
  resource's `:plan` generic action.
  """

  alias Ash.Error.Action.InvalidArgument

  @spec run(list(map())) :: {:ok, map()} | {:error, InvalidArgument.t()}
  def run(targets) when is_list(targets) and targets != [] do
    targets
    |> Enum.reduce_while({:ok, [], 0, MapSet.new()}, &validate_target/2)
    |> case do
      {:ok, names, total, _seen} ->
        {:ok,
         %{
           total_slots: total,
           node_names: Enum.sort(names),
           target_count: length(names)
         }}

      {:error, _} = error ->
        error
    end
  end

  def run(_targets) do
    {:error, invalid_argument("targets cannot be empty")}
  end

  defp validate_target(target, {:ok, names, total, seen}) do
    node_name = fetch(target, :node_name)
    slots = fetch(target, :slots)

    cond do
      not (is_binary(node_name) and node_name != "") ->
        {:halt, {:error, invalid_argument("each target must have a node_name")}}

      not (is_integer(slots) and slots > 0) ->
        {:halt, {:error, invalid_argument("each target's slots must be a positive integer")}}

      MapSet.member?(seen, node_name) ->
        {:halt, {:error, invalid_argument("duplicate node_name: #{node_name}")}}

      true ->
        {:cont, {:ok, [node_name | names], total + slots, MapSet.put(seen, node_name)}}
    end
  end

  defp fetch(target, key) when is_map(target) do
    Map.get(target, key) || Map.get(target, to_string(key))
  end

  defp fetch(_target, _key), do: nil

  defp invalid_argument(message) do
    InvalidArgument.exception(field: :targets, message: message)
  end
end
