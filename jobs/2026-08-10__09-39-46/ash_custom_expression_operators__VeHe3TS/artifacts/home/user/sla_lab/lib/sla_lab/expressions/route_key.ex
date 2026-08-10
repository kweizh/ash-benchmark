defmodule SlaLab.Expressions.RouteKey do
  use Ash.CustomExpression,
    name: :route_key,
    arguments: [
      [:string, :string]
    ]

  def expression(Ash.DataLayer.Ets, [left, right]) do
    {:ok, expr(fragment(&__MODULE__.compute/2, ^left, ^right))}
  end

  def expression(Ash.DataLayer.Simple, [left, right]) do
    {:ok, expr(fragment(&__MODULE__.compute/2, ^left, ^right))}
  end

  def expression(_data_layer, _args), do: :unknown

  @doc false
  def compute(nil, _right), do: nil
  def compute(_left, nil), do: nil

  def compute(left, right) do
    a = String.upcase(left)
    b = String.upcase(right)

    if a <= b do
      "#{a}|#{b}"
    else
      "#{b}|#{a}"
    end
  end
end
