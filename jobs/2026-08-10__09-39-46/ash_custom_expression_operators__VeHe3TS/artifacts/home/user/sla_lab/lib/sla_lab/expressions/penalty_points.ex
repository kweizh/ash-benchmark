defmodule SlaLab.Expressions.PenaltyPoints do
  @moduledoc """
  A custom query function for computing penalty points.

  Constructed programmatically with `Ash.Query.Function.new/2`.
  """

  @behaviour Ash.Query.Function

  @struct_fields [
    :arguments,
    name: :penalty_points,
    embedded?: false,
    __function__?: true,
    __predicate__?: false,
    extra: %{}
  ]

  defstruct @struct_fields

  defimpl Inspect do
    import Inspect.Algebra

    def inspect(%{arguments: args, name: name}, opts) do
      concat(
        to_string(name),
        container_doc("(", args, ")", opts, &to_doc/2, separator: ",")
      )
    end
  end

  @impl true
  def name, do: :penalty_points

  @impl true
  def args, do: [[:integer, :integer]]

  @impl true
  def returns, do: [:integer]

  @impl true
  def predicate?, do: false

  @impl true
  def private?, do: false

  @impl true
  def eager_evaluate?, do: true

  @impl true
  def evaluate_nil_inputs?, do: false

  @impl true
  def can_return_nil?(_func), do: true

  @impl true
  def new(args) do
    {:ok, struct(__MODULE__, arguments: args)}
  end

  @impl true
  def evaluate(%__MODULE__{arguments: [late_hours, weight]}) do
    if weight < 0 do
      {:error, "penalty weight must not be negative"}
    else
      cond do
        late_hours <= 0 ->
          {:known, 0}

        late_hours <= 24 ->
          {:known, late_hours * weight}

        true ->
          {:known, 24 * weight + (late_hours - 24) * weight * 2}
      end
    end
  end

  @impl true
  def partial_evaluate(func), do: {:ok, func}
end
