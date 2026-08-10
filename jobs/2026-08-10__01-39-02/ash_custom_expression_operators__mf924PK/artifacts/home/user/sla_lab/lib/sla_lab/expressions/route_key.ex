defmodule SlaLab.Expressions.RouteKey do
  use Ash.CustomExpression,
    name: :route_key,
    arguments: [
      [:string, :string]
    ]

  def expression(data_layer, [left, right]) when data_layer in [Ash.DataLayer.Ets, Ash.DataLayer.Simple] do
    import Ash.Expr
    {:ok, expr(fragment(&__MODULE__.route_key/2, ^left, ^right))}
  end

  def expression(_data_layer, _arguments), do: :unknown

  def route_key(nil, _), do: nil
  def route_key(_, nil), do: nil
  def route_key(left, right) when is_binary(left) and is_binary(right) do
    l = String.upcase(left)
    r = String.upcase(right)
    if l <= r do
      l <> "|" <> r
    else
      r <> "|" <> l
    end
  end
end
