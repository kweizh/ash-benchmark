defmodule SlaLab.Expressions.PenaltyPoints do
  @moduledoc """
  A custom Ash query function, `penalty_points/2`, that computes a penalty
  score for a late delivery given the number of hours late and a per-hour
  weight.

  Unlike `SlaLab.Expressions.RouteKey` and `SlaLab.Expressions.RatioBps`,
  this is not registered as a named custom expression. Instead it is meant
  to be constructed programmatically with `Ash.Query.Function.new/2` and
  embedded as a node inside an expression (e.g. via the `^` pin operator).
  """

  use Ash.Query.Function, name: :penalty_points

  @impl Ash.Query.Function
  def args, do: [[:integer, :integer]]

  @impl Ash.Query.Function
  def returns, do: [:integer]

  @impl Ash.Query.Function
  def evaluate(%{arguments: [late_hours, weight]})
      when is_integer(late_hours) and is_integer(weight) do
    cond do
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

  def evaluate(_), do: :unknown
end
