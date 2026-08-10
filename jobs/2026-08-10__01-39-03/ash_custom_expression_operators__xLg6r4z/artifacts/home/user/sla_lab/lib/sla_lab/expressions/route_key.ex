defmodule SlaLab.Expressions.RouteKey do
  @moduledoc """
  A reusable Ash expression building block that computes a canonical,
  order-independent "route key" from two zone codes.

  `route_key(left, right)` is `nil` if either argument is `nil`. Otherwise
  both arguments are upper-cased and joined with a single `"|"`, with the
  lexicographically smaller upper-cased value first, so the result does not
  depend on the order the arguments were given in.
  """

  use Ash.CustomExpression,
    name: :route_key,
    arguments: [[:string, :string]]

  @impl Ash.CustomExpression
  def expression(data_layer, [left, right])
      when data_layer in [Ash.DataLayer.Ets, Ash.DataLayer.Simple] do
    {:ok, expr(fragment(&__MODULE__.route_key/2, ^left, ^right))}
  end

  def expression(_data_layer, _arguments), do: :unknown

  @doc "Computes the canonical route key for two zone codes."
  @spec route_key(String.t() | nil, String.t() | nil) :: String.t() | nil
  def route_key(nil, _right), do: nil
  def route_key(_left, nil), do: nil

  def route_key(left, right) do
    [String.upcase(left), String.upcase(right)]
    |> Enum.sort()
    |> Enum.join("|")
  end
end
