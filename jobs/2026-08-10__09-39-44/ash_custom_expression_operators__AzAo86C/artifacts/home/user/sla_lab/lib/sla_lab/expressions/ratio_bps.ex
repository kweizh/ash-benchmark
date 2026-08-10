defmodule SlaLab.Expressions.RatioBps do
  @moduledoc """
  A custom Ash expression that computes a ratio in basis points.

  `ratio_bps(numerator, denominator)` returns `nil` when either argument is
  `nil` or the denominator is `0`.  Otherwise it computes
  `numerator * 10_000 / denominator`, rounded to the nearest whole number with
  exact halves rounded **up** (towards positive infinity), and clamped into the
  closed range `0..20_000`.  The result is always an Elixir integer.
  """

  use Ash.CustomExpression,
    name: :ratio_bps,
    arguments: [[:integer, :integer]]

  import Ash.Expr, only: [expr: 1]

  @impl Ash.CustomExpression
  def expression(Ash.DataLayer.Ets, [numerator, denominator]) do
    {:ok, expr(fragment(&__MODULE__.compute/2, ^numerator, ^denominator))}
  end

  @impl Ash.CustomExpression
  def expression(Ash.DataLayer.Simple, [numerator, denominator]) do
    {:ok, expr(fragment(&__MODULE__.compute/2, ^numerator, ^denominator))}
  end

  @impl Ash.CustomExpression
  def expression(_data_layer, _args), do: :unknown

  @doc """
  Computes the ratio in basis points.

  Returns `nil` when either argument is `nil` or the denominator is `0`.
  Otherwise returns `round_half_up(numerator * 10_000 / denominator)` clamped
  to `0..20_000` as an integer.
  """
  def compute(nil, _), do: nil
  def compute(_, nil), do: nil
  def compute(_, 0), do: nil

  def compute(numerator, denominator) do
    scaled = numerator * 10_000

    # Round to nearest with exact halves rounded up (towards +inf).
    # floor((2 * scaled + denominator) / (2 * denominator)) is the
    # standard round-half-up formula and works for negative numerators
    # too (denominators are never negative in the verified scenarios).
    rounded = Integer.floor_div(2 * scaled + denominator, 2 * denominator)

    min(20_000, max(0, rounded))
  end
end
