defmodule ThreadGraph.Forum.LoadCounter do
  @moduledoc """
  A tiny global invocation counter.

  It is deliberately process independent so that a counter bumped inside a data
  loading callback can be observed from anywhere in the VM.

  DO NOT MODIFY THIS MODULE.
  """

  @key {__MODULE__, :counts}

  @doc "Clears every counter."
  @spec reset() :: :ok
  def reset do
    :persistent_term.put(@key, %{})
    :ok
  end

  @doc "Increments the counter stored under `key`."
  @spec bump(atom()) :: :ok
  def bump(key) when is_atom(key) do
    counts = :persistent_term.get(@key, %{})
    :persistent_term.put(@key, Map.update(counts, key, 1, &(&1 + 1)))
    :ok
  end

  @doc "Returns the current value of the counter stored under `key`."
  @spec count(atom()) :: non_neg_integer()
  def count(key) when is_atom(key), do: Map.get(counts(), key, 0)

  @doc "Returns every counter as a map."
  @spec counts() :: %{optional(atom()) => non_neg_integer()}
  def counts, do: :persistent_term.get(@key, %{})
end
