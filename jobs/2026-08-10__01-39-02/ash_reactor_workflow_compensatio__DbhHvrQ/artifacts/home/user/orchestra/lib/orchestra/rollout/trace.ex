defmodule Orchestra.Rollout.Trace do
  use GenServer

  def start_link(init_arg) do
    GenServer.start_link(__MODULE__, init_arg, name: __MODULE__)
  end

  def reset do
    GenServer.call(__MODULE__, :reset)
  end

  def entries do
    GenServer.call(__MODULE__, :entries)
  end

  def record(event, label) when is_atom(event) and is_binary(label) do
    GenServer.cast(__MODULE__, {:record, event, label})
  end

  # GenServer callbacks

  @impl true
  def init(_init_arg) do
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
  def handle_cast({:record, event, label}, state) do
    {:noreply, [{event, label} | state]}
  end
end
