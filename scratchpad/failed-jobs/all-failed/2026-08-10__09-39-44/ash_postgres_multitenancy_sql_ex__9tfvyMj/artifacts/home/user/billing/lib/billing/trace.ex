defmodule Billing.Trace do
  @moduledoc """
  A tiny ordered, cross-process trace buffer used to observe the order in which
  lifecycle hooks execute.

  This module is provided for you. Do not change its public API.
  """
  use Agent

  def start_link(_opts \\ []) do
    Agent.start_link(fn -> [] end, name: __MODULE__)
  end

  @doc "Appends `entry` to the trace."
  def record(entry) do
    Agent.update(__MODULE__, fn entries -> [entry | entries] end)
    entry
  end

  @doc "Returns every recorded entry, oldest first."
  def entries do
    Agent.get(__MODULE__, &Enum.reverse/1)
  end

  @doc "Clears the trace."
  def reset do
    Agent.update(__MODULE__, fn _ -> [] end)
    :ok
  end
end
