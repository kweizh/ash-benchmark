defmodule Verify do
  import Ash.Expr
  require Ash.Query

  def check(label, fun) do
    IO.puts("\n=== #{label} ===")
    fun.()
  end

  def error_info({:error, %Ash.Error.Invalid{errors: errors}}) do
    Enum.map(errors, fn e ->
      %{field: Map.get(e, :field), message: Map.get(e, :message), kind: e.__struct__}
    end)
  end

  def error_info(other) do
    {:not_invalid, other}
  end

  def run do
    Application.ensure_all_started(:logistics)

    Logistics.Repo.query!("TRUNCATE carriers, warehouses, shipments, parcels, shipment_legs RESTART IDENTITY CASCADE", [], log: false)

    check("1. Carrier base_filter: retired carrier not returned", fn ->
      {:ok, carrier} = Ash.create(Logistics.Freight.Carrier, %{code: "ABC", name: "Alpha"}, authorize?: false)
      Logistics.Repo.query!("UPDATE carriers SET retired_at = now() WHERE id::text = $1", [carrier.id], log: false)
      {:ok, result} = Ash.read(Logistics.Freight.Carrier, authorize?: false)
      IO.inspect(result, label: "read result (should be [])")
    end)

    check("2. Unique carrier code case-insensitive", fn ->
      Ash.create(Logistics.Freight.Carrier, %{code: "UNIQ", name: "U1"}, authorize?: false)
      res = Ash.create(Logistics.Freight.Carrier, %{code: "uniq", name: "U2"}, authorize?: false)
      IO.inspect(error_info(res), label: "error")
    end)

    check("3. Carrier code collides with retired carrier - accepted", fn ->
      # Retire the existing live 'UNIQ' carrier first
      Logistics.Repo.query!("UPDATE carriers SET retired_at = now() WHERE code::text = 'UNIQ' AND retired_at IS NULL", [], log: false)
      res = Ash.create(Logistics.Freight.Carrier, %{code: "UNIQ", name: "Reused"}, authorize?: false)
      IO.inspect(elem(res, 0), label: "result (should be :ok)")
    end)

    check("4. Unique warehouse active code", fn ->
      Ash.create(Logistics.Freight.Warehouse, %{code: "WH1", name: "W1", region: "R1", capacity_parcels: 10}, authorize?: false)
      res = Ash.create(Logistics.Freight.Warehouse, %{code: "WH1", name: "W2", region: "R2", capacity_parcels: 5}, authorize?: false)
      IO.inspect(error_info(res), label: "error")
    end)

    check("5. Warehouse code collides with decommissioned - accepted", fn ->
      Logistics.Repo.query!("UPDATE warehouses SET decommissioned = true WHERE code = 'WH1'", [], log: false)
      res = Ash.create(Logistics.Freight.Warehouse, %{code: "WH1", name: "W3", region: "R3", capacity_parcels: 3}, authorize?: false)
      IO.inspect(elem(res, 0), label: "result (should be :ok)")
    end)

    check("6. Unique shipment reference", fn ->
      {:ok, c} = Ash.create(Logistics.Freight.Carrier, %{code: "CARR", name: "Carrier"}, authorize?: false)
      Ash.create(Logistics.Freight.Shipment, %{reference: "REF1", carrier_id: c.id}, authorize?: false)
      res = Ash.create(Logistics.Freight.Shipment, %{reference: "REF1", carrier_id: c.id}, authorize?: false)
      IO.inspect(error_info(res), label: "error")
    end)

    check("7. Unique parcel tracking_code", fn ->
      {:ok, [ship]} = Ash.read(Logistics.Freight.Shipment, authorize?: false)
      Ash.create(Logistics.Freight.Parcel, %{tracking_code: "TC1", weight_grams: 100, shipment_id: ship.id}, authorize?: false)
      res = Ash.create(Logistics.Freight.Parcel, %{tracking_code: "TC1", weight_grams: 200, shipment_id: ship.id}, authorize?: false)
      IO.inspect(error_info(res), label: "error")
    end)

    check("8. Single fragile parcel per shipment", fn ->
      {:ok, [ship]} = Ash.read(Logistics.Freight.Shipment, authorize?: false)
      Ash.create(Logistics.Freight.Parcel, %{tracking_code: "FR1", weight_grams: 100, fragile: true, shipment_id: ship.id}, authorize?: false)
      res = Ash.create(Logistics.Freight.Parcel, %{tracking_code: "FR2", weight_grams: 100, fragile: true, shipment_id: ship.id}, authorize?: false)
      IO.inspect(error_info(res), label: "error")
    end)

    check("9. Unique shipment_leg sequence", fn ->
      {:ok, [ship]} = Ash.read(Logistics.Freight.Shipment, authorize?: false)
      {:ok, wh} = Ash.create(Logistics.Freight.Warehouse, %{code: "WHL", name: "WL", region: "R", capacity_parcels: 1}, authorize?: false)
      Ash.create(Logistics.Freight.ShipmentLeg, %{sequence: 1, shipment_id: ship.id, warehouse_id: wh.id}, authorize?: false)
      res = Ash.create(Logistics.Freight.ShipmentLeg, %{sequence: 1, shipment_id: ship.id, warehouse_id: wh.id}, authorize?: false)
      IO.inspect(error_info(res), label: "error")
    end)

    check("10. Destroy carrier referenced by shipment", fn ->
      {:ok, c2} = Ash.create(Logistics.Freight.Carrier, %{code: "CDEST", name: "CD"}, authorize?: false)
      Ash.create(Logistics.Freight.Shipment, %{reference: "REFDEST", carrier_id: c2.id}, authorize?: false)
      {:ok, carriers} = Ash.read(Logistics.Freight.Carrier, authorize?: false)
      carrier = Enum.find(carriers, &(to_string(&1.code) == "CDEST"))
      res = Ash.destroy(carrier, authorize?: false)
      IO.inspect(error_info(res), label: "error")
    end)

    check("11. Destroy warehouse referenced by shipment_leg", fn ->
      {:ok, c3} = Ash.create(Logistics.Freight.Carrier, %{code: "C3", name: "C3"}, authorize?: false)
      {:ok, s3} = Ash.create(Logistics.Freight.Shipment, %{reference: "REF3", carrier_id: c3.id}, authorize?: false)
      {:ok, whd} = Ash.create(Logistics.Freight.Warehouse, %{code: "WHD", name: "WD", region: "R", capacity_parcels: 1}, authorize?: false)
      Ash.create(Logistics.Freight.ShipmentLeg, %{sequence: 1, shipment_id: s3.id, warehouse_id: whd.id}, authorize?: false)
      res = Ash.destroy(whd, authorize?: false)
      IO.inspect(error_info(res), label: "error")
    end)

    check("12. Check constraint: warehouse capacity negative", fn ->
      res = Ash.create(Logistics.Freight.Warehouse, %{code: "WHNEG", name: "WN", region: "R", capacity_parcels: -1}, authorize?: false)
      IO.inspect(error_info(res), label: "error")
    end)

    check("13. Check constraint: shipment declared value negative", fn ->
      {:ok, c} = Ash.create(Logistics.Freight.Carrier, %{code: "CVAL", name: "CV"}, authorize?: false)
      res = Ash.create(Logistics.Freight.Shipment, %{reference: "REFNEG", carrier_id: c.id, declared_value_cents: -5}, authorize?: false)
      IO.inspect(error_info(res), label: "error")
    end)

    check("14. Check constraint: parcel weight non-positive", fn ->
      {:ok, c} = Ash.create(Logistics.Freight.Carrier, %{code: "CW", name: "CW"}, authorize?: false)
      {:ok, s} = Ash.create(Logistics.Freight.Shipment, %{reference: "REFW", carrier_id: c.id}, authorize?: false)
      res = Ash.create(Logistics.Freight.Parcel, %{tracking_code: "TCW", weight_grams: 0, shipment_id: s.id}, authorize?: false)
      IO.inspect(error_info(res), label: "error")
    end)

    check("15. Check constraint: shipment_leg sequence < 1", fn ->
      {:ok, c} = Ash.create(Logistics.Freight.Carrier, %{code: "CS", name: "CS"}, authorize?: false)
      {:ok, s} = Ash.create(Logistics.Freight.Shipment, %{reference: "REFS", carrier_id: c.id}, authorize?: false)
      {:ok, wh} = Ash.create(Logistics.Freight.Warehouse, %{code: "WHS", name: "WS", region: "R", capacity_parcels: 1}, authorize?: false)
      res = Ash.create(Logistics.Freight.ShipmentLeg, %{sequence: 0, shipment_id: s.id, warehouse_id: wh.id}, authorize?: false)
      IO.inspect(error_info(res), label: "error")
    end)

    check("16. Intake action - success", fn ->
      {:ok, c} = Ash.create(Logistics.Freight.Carrier, %{code: "CINT", name: "CI"}, authorize?: false)
      res = Ash.create(Logistics.Freight.Shipment, %{reference: "INT1", carrier_id: c.id, declared_value_cents: 500, parcels: [%{tracking_code: "P1", weight_grams: 100}, %{tracking_code: "P2", weight_grams: 200, fragile: true}]}, action: :intake, authorize?: false)
      IO.inspect(elem(res, 0), label: "result (should be :ok)")
      {:ok, ship} = res
      loaded = Ash.load!(ship, [:parcel_count, :total_weight_grams, :heavy?])
      IO.inspect(loaded.parcel_count, label: "parcel_count (should be 2)")
      IO.inspect(loaded.total_weight_grams, label: "total_weight_grams (should be 300)")
      IO.inspect(loaded.heavy?, label: "heavy? (should be false)")
    end)

    check("17. Intake action - parcel rejected, transaction rollback", fn ->
      {:ok, c} = Ash.create(Logistics.Freight.Carrier, %{code: "CINT2", name: "CI2"}, authorize?: false)
      {:ok, s0} = Ash.create(Logistics.Freight.Shipment, %{reference: "INT0", carrier_id: c.id}, authorize?: false)
      Ash.create(Logistics.Freight.Parcel, %{tracking_code: "DUP", weight_grams: 100, shipment_id: s0.id}, authorize?: false)
      before_count = hd(hd(Logistics.Repo.query!("SELECT count(*) FROM shipments", [], log: false).rows))
      res = Ash.create(Logistics.Freight.Shipment, %{reference: "INT2", carrier_id: c.id, parcels: [%{tracking_code: "DUP", weight_grams: 100}]}, action: :intake, authorize?: false)
      IO.inspect(elem(res, 0), label: "result (should be :error)")
      after_count = hd(hd(Logistics.Repo.query!("SELECT count(*) FROM shipments", [], log: false).rows))
      IO.inspect({before_count, after_count}, label: "shipment counts (should be equal)")
      exists = hd(hd(Logistics.Repo.query!("SELECT count(*) FROM shipments WHERE reference = 'INT2'", [], log: false).rows))
      IO.inspect(exists, label: "INT2 exists (should be 0)")
    end)

    check("18. Aggregates and calculation in filter", fn ->
      res = Ash.Query.filter(Logistics.Freight.Shipment, expr(total_weight_grams > 5000)) |> Ash.read(authorize?: false)
      IO.inspect(elem(res, 0), label: "filter total_weight_grams > 5000")
      res2 = Ash.Query.filter(Logistics.Freight.Shipment, expr(parcel_count > 0)) |> Ash.read(authorize?: false)
      IO.inspect(elem(res2, 0), label: "filter parcel_count > 0")
      res3 = Ash.Query.filter(Logistics.Freight.Shipment, expr(heavy? == true)) |> Ash.read(authorize?: false)
      IO.inspect(elem(res3, 0), label: "filter heavy? == true")
    end)

    check("19. Heavy shipment and heavy?", fn ->
      {:ok, c} = Ash.create(Logistics.Freight.Carrier, %{code: "CHV", name: "CHV"}, authorize?: false)
      {:ok, s} = Ash.create(Logistics.Freight.Shipment, %{reference: "HEAVY", carrier_id: c.id, parcels: [%{tracking_code: "H1", weight_grams: 3000}, %{tracking_code: "H2", weight_grams: 3000}]}, action: :intake, authorize?: false)
      loaded = Ash.load!(s, [:total_weight_grams, :heavy?, :parcel_count])
      IO.inspect(loaded.total_weight_grams, label: "total_weight_grams (should be 6000)")
      IO.inspect(loaded.heavy?, label: "heavy? (should be true)")
      IO.inspect(loaded.parcel_count, label: "parcel_count (should be 2)")
    end)

    IO.puts("\n=== DONE ===")
  end
end

Verify.run()
