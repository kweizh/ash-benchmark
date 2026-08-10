defmodule Orchestra.Rollout.Trace do
  @moduledoc """
  A process-safe, ordered trace of everything that happens during a rollout
  execution. Usable from any process, including ones spawned by `Reactor` for
  asynchronous steps.
  """
  use GenServer

  @doc false
  def start_link(_opts) do
    GenServer.start_link(__MODULE__, [], name: __MODULE__)
  end

  @doc "Clears the trace."
  @spec reset() :: :ok
  def reset do
    GenServer.call(__MODULE__, :reset)
  end

  @doc "Records a `{event, label}` entry onto the end of the trace."
  @spec record({atom(), String.t()}) :: :ok
  def record({_event, _label} = entry) do
    GenServer.call(__MODULE__, {:record, entry})
  end

  @doc "Returns all recorded entries, in the order they were recorded."
  @spec entries() :: [{atom(), String.t()}]
  def entries do
    GenServer.call(__MODULE__, :entries)
  end

  @impl true
  def init(_), do: {:ok, []}

  @impl true
  def handle_call(:reset, _from, _state), do: {:reply, :ok, []}

  def handle_call({:record, entry}, _from, state), do: {:reply, :ok, [entry | state]}

  def handle_call(:entries, _from, state), do: {:reply, Enum.reverse(state), state}
end
