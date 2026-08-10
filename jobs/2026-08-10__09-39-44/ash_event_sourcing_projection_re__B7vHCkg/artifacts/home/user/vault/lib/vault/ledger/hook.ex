defmodule Vault.Ledger.Hook do
  @moduledoc """
  A test seam used by the evaluation suite to interleave work into long running
  operations, and to observe that those operations reached a documented point.

  `run/1` records that the labelled point was reached and, if a callback has been
  registered for that label in the current process, invokes it.

  Do not modify this module.
  """

  @doc "Register a zero-arity callback to be invoked the next time `run/1` is called with `label`."
  @spec set(atom(), (-> any())) :: :ok
  def set(label, fun) when is_atom(label) and is_function(fun, 0) do
    Process.put({__MODULE__, :callback, label}, fun)
    :ok
  end

  @doc "Remove any callback registered for `label` and reset its invocation counter."
  @spec clear(atom()) :: :ok
  def clear(label) when is_atom(label) do
    Process.delete({__MODULE__, :callback, label})
    Process.delete({__MODULE__, :count, label})
    :ok
  end

  @doc "How many times `run/1` has been called with `label` in this process."
  @spec count(atom()) :: non_neg_integer()
  def count(label) when is_atom(label) do
    Process.get({__MODULE__, :count, label}, 0)
  end

  @doc "Mark the labelled point as reached and invoke the registered callback, if any."
  @spec run(atom()) :: :ok
  def run(label) when is_atom(label) do
    Process.put({__MODULE__, :count, label}, count(label) + 1)

    case Process.get({__MODULE__, :callback, label}) do
      fun when is_function(fun, 0) -> fun.()
      _ -> :ok
    end

    :ok
  end
end
