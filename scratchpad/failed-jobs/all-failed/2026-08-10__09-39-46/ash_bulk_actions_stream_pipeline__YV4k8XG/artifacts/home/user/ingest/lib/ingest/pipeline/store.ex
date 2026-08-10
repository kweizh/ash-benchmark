defmodule Ingest.Pipeline.Store do
  @moduledoc """
  Provides a way to reset all persisted records across all resources in the domain.
  """

  @doc """
  Removes every persisted record of every resource in the domain (meters included) and returns `:ok`.
  """
  def reset! do
    # Destroy all MeterRollup records
    Ingest.Pipeline.MeterRollup
    |> Ash.bulk_destroy!(:destroy, %{}, return_errors?: true)

    # Destroy all Reading records
    Ingest.Pipeline.Reading
    |> Ash.bulk_destroy!(:destroy, %{}, return_errors?: true)

    # Destroy all Meter records
    Ingest.Pipeline.Meter
    |> Ash.bulk_destroy!(:destroy, %{}, return_errors?: true)

    :ok
  end
end
