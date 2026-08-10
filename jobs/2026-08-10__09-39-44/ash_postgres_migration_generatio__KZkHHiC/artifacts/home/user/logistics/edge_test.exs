defmodule EdgeTest do
  require Ash.Query
  import Ash.Expr

  def run do
    Application.ensure_all_started(:logistics)
    Logistics.Repo.query!("TRUNCATE carriers, warehouses, shipments, parcels, shipment_legs RESTART IDENTITY CASCADE", [], log: false)

    {:ok, c} = Ash.create(Logistics.Freight.Carrier, %{code: "EC", name: "EC"}, authorize?: false)
    # Shipment with no parcels
    {:ok, s} = Ash.create(Logistics.Freight.Shipment, %{reference: "NOPARCEL", carrier_id: c.id}, authorize?: false)
    loaded = Ash.load!(s, [:total_weight_grams, :heavy?, :parcel_count])
    IO.inspect(loaded.total_weight_grams, label: "total_weight_grams (no parcels)")
    IO.inspect(loaded.heavy?, label: "heavy? (no parcels, should be false)")
    IO.inspect(loaded.parcel_count, label: "parcel_count (no parcels, should be 0)")

    # Filter heavy? == false
    result = Logistics.Freight.Shipment
      |> Ash.Query.filter(expr(heavy? == false))
      |> Ash.read!(authorize?: false)
    IO.inspect(length(result), label: "filter heavy? == false (should be >= 1)")

    # Update action accepts all columns
    {:ok, s2} = Ash.update(s, %{reference: "UPDATED", status: :in_transit, declared_value_cents: 100, carrier_id: c.id}, authorize?: false)
    IO.inspect(s2.reference, label: "updated reference (should be UPDATED)")
    IO.inspect(s2.status, label: "updated status (should be :in_transit)")

    IO.puts("DONE")
  end
end

EdgeTest.run()
