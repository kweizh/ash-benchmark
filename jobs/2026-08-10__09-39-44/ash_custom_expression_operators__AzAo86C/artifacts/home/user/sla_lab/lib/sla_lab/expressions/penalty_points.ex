defmodule SlaLab.Expressions.PenaltyPoints do
  @moduledoc """
  An Ash query function that computes penalty points for a late delivery.

  `penalty_points(late_hours, weight)` is constructed programmatically with
  `Ash.Query.Function.new/2` and used as a node inside expressions.

  * `late_hours <= 0` -> `0`
  * `1 <= late_hours <= 24` -> `late_hours * weight`
  * `late_hours > 24` -> `24 * weight + (late_hours - 24) * weight * 2`
  * `weight < 0` -> `{:error, "penalty weight must not be negative"}`
  * any non-integer argument -> `:unknown`
  * any `nil` argument -> `nil` (never evaluated)
  """

  use Ash.Query.Function, name: :penalty_points

  @impl Ash.Query.Function
  def args, do: [[:integer, :integer]]

  @impl Ash.Query.Function
  def returns, do: [:integer]

  @impl Ash.Query.Function
  def predicate?, do: false

  @impl Ash.Query.Function
  def evaluate(%{arguments: [late_hours, weight]}) do
    cond do
      not is_integer(late_hours) or not is_integer(weight) ->
        :unknown

      weight < 0 ->
        {:error, "penalty weight must not be negative"}

      late_hours <= 0 ->
        {:known, 0}

      late_hours <= 24 ->
        {:known, late_hours * weight}

      true ->
        {:known, 24 * weight + (late_hours - 24) * weight * 2}
    end
  end
end
