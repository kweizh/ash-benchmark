defmodule SlaLab.Expressions.RatioBps do
  @moduledoc """
  A reusable Ash expression building block that computes the ratio of two
  integers expressed in basis points (1/100th of a percent).

  `ratio_bps(numerator, denominator)` is `nil` if either argument is `nil`
  or the denominator is `0`. Otherwise it is
  `numerator * 10_000 / denominator`, rounded to the nearest whole number
  with exact halves rounded up (towards positive infinity), and then
  clamped into the closed range `0..20_000`. The result is always an
  Elixir integer, never a float.
  """

  use Ash.CustomExpression,
    name: :ratio_bps,
    arguments: [[:integer, :integer]]

  @min_bps 0
  @max_bps 20_000

  @impl Ash.CustomExpression
  def expression(data_layer, [numerator, denominator])
      when data_layer in [Ash.DataLayer.Ets, Ash.DataLayer.Simple] do
    {:ok, expr(fragment(&__MODULE__.ratio_bps/2, ^numerator, ^denominator))}
  end

  def expression(_data_layer, _arguments), do: :unknown

  @doc "Computes the ratio of numerator over denominator, in basis points."
  @spec ratio_bps(integer | nil, integer | nil) :: integer | nil
  def ratio_bps(nil, _denominator), do: nil
  def ratio_bps(_numerator, nil), do: nil
  def ratio_bps(_numerator, 0), do: nil

  def ratio_bps(numerator, denominator) do
    raw = numerator * 10_000

    (2 * raw + denominator)
    |> Integer.floor_div(2 * denominator)
    |> max(@min_bps)
    |> min(@max_bps)
  end
end
