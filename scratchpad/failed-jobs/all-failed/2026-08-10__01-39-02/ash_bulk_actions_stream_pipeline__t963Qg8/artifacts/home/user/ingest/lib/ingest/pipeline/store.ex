defmodule Ingest.Pipeline.Store do
  def reset! do
    resources = [
      Ingest.Pipeline.Meter,
      Ingest.Pipeline.Reading,
      Ingest.Pipeline.MeterRollup
    ]

    Enum.each(resources, fn resource ->
      configured_table = Ash.DataLayer.Ets.Info.table(resource)

      case Process.get({:ash_ets_table, configured_table, nil}) do
        nil ->
          :ok

        %ETS.Set{table: ets_table} ->
          :ets.delete_all_objects(ets_table)
          :ok

        _ ->
          # If for some reason it's not in the process dictionary, we can also read and destroy all
          case Ash.read(resource) do
            {:ok, records} ->
              Enum.each(records, &Ash.destroy!/1)

            _ ->
              :ok
          end
      end
    end)

    :ok
  end
end
