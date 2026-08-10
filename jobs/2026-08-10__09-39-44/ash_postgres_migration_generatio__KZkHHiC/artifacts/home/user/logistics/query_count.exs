defmodule QueryCount do
  require Ash.Query
  import Ash.Expr

  def run do
    Application.ensure_all_started(:logistics)
    Logistics.Repo.query!("TRUNCATE carriers, warehouses, shipments, parcels, shipment_legs RESTART IDENTITY CASCADE", [], log: false)

    {:ok, c} = Ash.create(Logistics.Freight.Carrier, %{code: "QC", name: "QC"}, authorize?: false)
    {:ok, _} = Ash.create(Logistics.Freight.Shipment, %{reference: "QC1", carrier_id: c.id, parcels: [%{tracking_code: "QCP1", weight_grams: 100}]}, action: :intake, authorize?: false)
    {:ok, _} = Ash.create(Logistics.Freight.Shipment, %{reference: "QC2", carrier_id: c.id, parcels: [%{tracking_code: "QCP2", weight_grams: 100}, %{tracking_code: "QCP3", weight_grams: 100}]}, action: :intake, authorize?: false)

    # Count queries for a filtered read that also loads parcel_count
    :telemetry.attach_many(
      "query-counter",
      [[:logistics, :repo, :query]],
      fn _event, _measurements, _metadata, pid ->
        counts = Process.get(:query_counts, 0)
        Process.put(:query_counts, counts + 1)
      end,
      nil
    )

    Process.put(:query_counts, 0)
    result = Logistics.Freight.Shipment
      |> Ash.Query.filter(expr(parcel_count > 0))
      |> Ash.Query.load(:parcel_count)
      |> Ash.read!(authorize?: false)
    count = Process.get(:query_counts)
    IO.puts("Filtered read + load parcel_count: #{count} query/queries (expect 1)")
    IO.inspect(length(result), label: "results")
    IO.inspect(Enum.map(result, & &1.parcel_count), label: "parcel_counts")

    Process.put(:query_counts, 0)
    result2 = Logistics.Freight.Shipment
      |> Ash.Query.filter(expr(heavy? == true))
      |> Ash.Query.load([:parcel_count, :heavy?])
      |> Ash.read!(authorize?: false)
    count2 = Process.get(:query_counts)
    IO.puts("Filter heavy? + load parcel_count & heavy?: #{count2} query/queries (expect 1)")
    IO.inspect(length(result2), label: "heavy results")

    :telemetry.detach("query-counter")
    IO.puts("DONE")
  end
end

QueryCount.run()
