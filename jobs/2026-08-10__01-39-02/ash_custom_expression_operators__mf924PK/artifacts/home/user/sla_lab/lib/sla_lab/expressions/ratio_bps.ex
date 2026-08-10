defmodule SlaLab.Expressions.RatioBps do
  use Ash.CustomExpression,
    name: :ratio_bps,
    arguments: [
      [:integer, :integer]
    ]

  def expression(data_layer, [numerator, denominator]) when data_layer in [Ash.DataLayer.Ets, Ash.DataLayer.Simple] do
    import Ash.Expr
    {:ok, expr(fragment(&__MODULE__.ratio_bps/2, ^numerator, ^denominator))}
  end

  def expression(_data_layer, _arguments), do: :unknown

  def ratio_bps(nil, _), do: nil
  def ratio_bps(_, nil), do: nil
  def ratio_bps(_, 0), do: nil
  def ratio_bps(numerator, denominator) when is_integer(numerator) and is_integer(denominator) do
    f = (numerator * 10_000) / denominator
    rounded = trunc(Float.floor(f + 0.5))
    clamp(rounded, 0, 20_000)
  end

  defp clamp(val, min, max) do
    cond do
      val < min -> min
      val > max -> max
      true -> val
    end
  end
end
