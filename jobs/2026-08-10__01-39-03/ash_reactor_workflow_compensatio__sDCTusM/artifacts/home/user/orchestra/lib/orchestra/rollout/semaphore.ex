defmodule Orchestra.Rollout.Semaphore do
  @moduledoc """
  A tiny counting semaphore used to bound the number of concurrent node
  deployments in flight at any one time.
  """
  use GenServer

  @limit 2

  @doc false
  def start_link(_opts) do
    GenServer.start_link(__MODULE__, %{available: @limit, waiting: :queue.new()}, name: __MODULE__)
  end

  @doc "Blocks until a permit is available, then acquires it."
  @spec acquire() :: :ok
  def acquire, do: GenServer.call(__MODULE__, :acquire, :infinity)

  @doc "Releases a previously acquired permit."
  @spec release() :: :ok
  def release, do: GenServer.cast(__MODULE__, :release)

  @impl true
  def init(state), do: {:ok, state}

  @impl true
  def handle_call(:acquire, _from, %{available: available} = state) when available > 0 do
    {:reply, :ok, %{state | available: available - 1}}
  end

  def handle_call(:acquire, from, %{waiting: waiting} = state) do
    {:noreply, %{state | waiting: :queue.in(from, waiting)}}
  end

  @impl true
  def handle_cast(:release, %{waiting: waiting} = state) do
    case :queue.out(waiting) do
      {{:value, from}, rest} ->
        GenServer.reply(from, :ok)
        {:noreply, %{state | waiting: rest}}

      {:empty, _} ->
        {:noreply, %{state | available: state.available + 1}}
    end
  end
end
