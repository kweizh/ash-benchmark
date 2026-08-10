defmodule Orchestra.Rollout.Actions.PlanRollout do
  @moduledoc false

  use Ash.Resource.Actions.Implementation

  alias Ash.Error.Action.InvalidArgument

  @impl true
  def run(input, _opts, _context) do
    targets = input.arguments.targets

    cond do
      is_nil(targets) or targets == [] ->
        {:error, invalid(:targets, "must not be empty")}

      Enum.any?(targets, &invalid_slots?/1) ->
        {:error, invalid(:targets, "every target must have a positive integer `slots`")}

      duplicate_names?(targets) ->
        {:error, invalid(:targets, "target node names must be unique")}

      true ->
        node_names =
          targets
          |> Enum.map(&Map.fetch!(&1, :node_name))
          |> Enum.sort()

        total_slots =
          targets
          |> Enum.map(&Map.fetch!(&1, :slots))
          |> Enum.sum()

        {:ok, %{total_slots: total_slots, node_names: node_names, target_count: length(targets)}}
    end
  end

  defp invalid(:targets, message), do: InvalidArgument.exception(field: :targets, message: message)

  defp invalid_slots?(%{slots: slots}) when is_integer(slots) and slots > 0, do: false
  defp invalid_slots?(_), do: true

  defp duplicate_names?(targets) do
    names = Enum.map(targets, &Map.fetch!(&1, :node_name))
    length(names) != length(Enum.uniq(names))
  end
end
