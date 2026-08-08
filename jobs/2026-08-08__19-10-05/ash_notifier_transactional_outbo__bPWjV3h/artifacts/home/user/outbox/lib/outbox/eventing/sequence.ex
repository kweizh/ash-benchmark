defmodule Outbox.Eventing.Sequence do
  @moduledoc """
  Atomic sequence number generation for outbox entries.

  Uses an ETS table to store counters, providing atomic increment
  via `:ets.update_counter/3`.
  """

  @table_name :outbox_sequences

  @doc """
  Initialises the sequence table. Must be called before any `next/3` calls.
  """
  def init do
    unless :ets.whereis(@table_name) != :undefined do
      @table_name =
        :ets.new(@table_name, [
          :set,
          :public,
          :named_table,
          {:read_concurrency, true},
          {:write_concurrency, true}
        ])

      # Global sequence starts at 0, so first call yields 1
      :ets.insert(@table_name, {:global, 0})
    end

    :ok
  end

  @doc """
  Atomically increments and returns the next global and per-aggregate sequence numbers.

  Returns `{global_sequence, aggregate_sequence}`.
  """
  def next(_resource, aggregate_type, aggregate_id) do
    # Atomically increment global counter
    global = :ets.update_counter(@table_name, :global, {2, 1})

    # Atomically increment per-aggregate counter
    agg_key = {aggregate_type, aggregate_id}

    agg_seq =
      try do
        :ets.update_counter(@table_name, agg_key, {2, 1})
      rescue
        ArgumentError ->
          # Key doesn't exist yet, insert starting at 1
          :ets.insert(@table_name, {agg_key, 1})
          1
      end

    {global, agg_seq}
  end

  @doc """
  Resets all sequence counters to their initial state.
  """
  def reset do
    :ets.delete_all_objects(@table_name)
    :ets.insert(@table_name, {:global, 0})
    :ok
  end
end
