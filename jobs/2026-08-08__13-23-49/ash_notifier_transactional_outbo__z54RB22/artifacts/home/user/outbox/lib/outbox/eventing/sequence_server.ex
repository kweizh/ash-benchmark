defmodule Outbox.Eventing.SequenceServer do
  @moduledoc """
  Atomic sequence generator for global and per-aggregate sequence numbers.
  """

  use GenServer

  def start_link(_opts) do
    GenServer.start_link(__MODULE__, nil, name: __MODULE__)
  end

  def next_sequences(aggregate_type, aggregate_id) do
    GenServer.call(__MODULE__, {:next_sequences, aggregate_type, aggregate_id})
  end

  def current_sequence do
    GenServer.call(__MODULE__, :current_sequence)
  end

  def reset do
    GenServer.call(__MODULE__, :reset)
  end

  # GenServer Callbacks

  @impl true
  def init(_) do
    {:ok, %{global_sequence: 0, aggregate_sequences: %{}}}
  end

  @impl true
  def handle_call({:next_sequences, aggregate_type, aggregate_id}, _from, state) do
    new_global = state.global_sequence + 1
    key = {aggregate_type, aggregate_id}
    new_agg = Map.get(state.aggregate_sequences, key, 0) + 1
    new_agg_seqs = Map.put(state.aggregate_sequences, key, new_agg)

    {:reply, {new_global, new_agg}, %{state | global_sequence: new_global, aggregate_sequences: new_agg_seqs}}
  end

  @impl true
  def handle_call(:current_sequence, _from, state) do
    {:reply, state.global_sequence, state}
  end

  @impl true
  def handle_call(:reset, _from, _state) do
    {:reply, :ok, %{global_sequence: 0, aggregate_sequences: %{}}}
  end
end
