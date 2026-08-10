defmodule SlaLab.Expressions.RouteKey do
  @moduledoc """
  A custom Ash expression that computes a canonical route key from two zone
  strings.

  `route_key(left, right)` upper-cases both arguments and joins them with a
  single `"|"`, placing the lexicographically smaller value first so that the
  result is independent of argument order.  Returns `nil` when either argument
  is `nil`.
  """

  use Ash.CustomExpression,
    name: :route_key,
    arguments: [[:string, :string]]

  import Ash.Expr, only: [expr: 1]

  @impl Ash.CustomExpression
  def expression(Ash.DataLayer.Ets, [left, right]) do
    {:ok, expr(fragment(&__MODULE__.compute/2, ^left, ^right))}
  end

  @impl Ash.CustomExpression
  def expression(Ash.DataLayer.Simple, [left, right]) do
    {:ok, expr(fragment(&__MODULE__.compute/2, ^left, ^right))}
  end

  @impl Ash.CustomExpression
  def expression(_data_layer, _args), do: :unknown

  @doc """
  Computes the canonical route key.

  Returns `nil` when either argument is `nil`.  Otherwise upper-cases both
  arguments and joins them with `"|"`, the smaller value first.
  """
  def compute(nil, _), do: nil
  def compute(_, nil), do: nil

  def compute(left, right) do
    left = String.upcase(left)
    right = String.upcase(right)

    if left <= right do
      left <> "|" <> right
    else
      right <> "|" <> left
    end
  end
end
