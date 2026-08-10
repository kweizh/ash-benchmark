defmodule SchedTest do
  require Ash.Query
  import Ash.Expr

  def run do
    Application.ensure_all_started(:logistics)
    Logistics.Repo.query!("TRUNCATE carriers, warehouses, shipments, parcels, shipment_legs RESTART IDENTITY CASCADE", [], log: false)

    {:ok, c} = Ash.create(Logistics.Freight.Carrier, %{code: "SC", name: "SC"}, authorize?: false)

    # Test scheduled_for with a DateTime (timestamptz column, :utc_datetime Ash type)
    dt = ~U[2026-09-15 10:30:00Z]
    {:ok, s} = Ash.create(Logistics.Freight.Shipment, %{reference: "SCHED1", carrier_id: c.id, scheduled_for: dt, status: :booked}, authorize?: false)
    IO.inspect(s.status, label: "status (should be :booked)")
    IO.inspect(s.scheduled_for, label: "scheduled_for (should be ~U[2026-09-15 10:30:00Z])")

    # Read back
    {:ok, [s2]} = Ash.read(Logistics.Freight.Shipment, authorize?: false)
    IO.inspect(s2.status, label: "read status (should be :booked)")
    IO.inspect(s2.scheduled_for, label: "read scheduled_for")

    # Filter on scheduled_for
    result = Logistics.Freight.Shipment
      |> Ash.Query.filter(expr(scheduled_for > ^~U[2026-01-01 00:00:00Z]))
      |> Ash.read!(authorize?: false)
    IO.inspect(length(result), label: "filter scheduled_for > 2026-01-01 (should be 1)")

    # Test booked_at default (now())
    {:ok, s3} = Ash.create(Logistics.Freight.Shipment, %{reference: "BOOKED1", carrier_id: c.id}, authorize?: false)
    IO.inspect(s3.booked_at, label: "booked_at (should be set to now)")

    # Test nil scheduled_for
    IO.inspect(s3.scheduled_for, label: "s3 scheduled_for (should be nil)")

    IO.puts("DONE")
  end
end

SchedTest.run()
