defmodule Orchestra.Rollout.Trace do
  @moduledoc """
  An ordered, process-independent record of what happened during a rollout run.

  The trace is backed by a single named `GenServer` so that it can be written to
  and read from any process — including the worker processes Reactor spawns for
  asynchronous steps. It is started under the application supervision tree, so
  it is available as soon as the `:orchestra` application has booted.
  """

  use GenServer

  @type entry :: {event :: atom, label :: String.t()}

  ## Public API

  @doc "Clears the trace and returns `:ok`."
  @spec reset :: :ok
  def reset do
    GenServer.call(__MODULE__, :reset)
  end

  @doc "Returns the recorded entries in the order they were recorded."
  @spec entries :: [entry]
  def entries do
    GenServer.call(__MODULE__, :entries)
  end

  @doc "Records a single entry. Safe to call from any process."
  @spec record(entry) :: :ok
  def record(entry) do
    GenServer.call(__MODULE__, {:record, entry})
  end

  ## GenServer callbacks

  @impl true
  def init(_arg) do
    {:ok, []}
  end

  @impl true
  def handle_call(:reset, _from, _state) do
    {:reply, :ok, []}
  end

  @impl true
  def handle_call(:entries, _from, state) do
    {:reply, Enum.reverse(state), state}
  end

  @impl true
  def handle_call({:record, entry}, _from, state) do
    {:reply, :ok, [entry | state]}
  end

  ## Supervisor helper

  @doc false
  def child_spec(_arg) do
    %{
      id: __MODULE__,
      start: {__MODULE__, :start_link, []},
      type: :worker,
      restart: :permanent
    }
  end

  @doc false
  def start_link(_arg \\ []) do
    GenServer.start_link(__MODULE__, [], name: __MODULE__)
  end
end
