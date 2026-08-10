defmodule SlaLab.Expressions.RatioBps do
  use Ash.CustomExpression,
    name: :ratio_bps,
    arguments: [
      [:integer, :integer]
    ]

  def expression(Ash.DataLayer.Ets, [numerator, denominator]) do
    {:ok, expr(fragment(&__MODULE__.compute/2, ^numerator, ^denominator))}
  end

  def expression(Ash.DataLayer.Simple, [numerator, denominator]) do
    {:ok, expr(fragment(&__MODULE__.compute/2, ^numerator, ^denominator))}
  end

  def expression(_data_layer, _args), do: :unknown

  @doc false
  def compute(nil, _denominator), do: nil
  def compute(_numerator, nil), do: nil
  def compute(_numerator, 0), do: nil

  def compute(numerator, denominator) do
    # numerator * 10_000 / denominator rounded to nearest whole number,
    # with exact halves rounded up (towards positive infinity)
    result =
      (numerator * 10_000 / denominator)
      |> Float.round()

    # Clamp into 0..20_000
    result
    |> max(0)
    |> min(20_000)
    |> trunc()
  end
end
