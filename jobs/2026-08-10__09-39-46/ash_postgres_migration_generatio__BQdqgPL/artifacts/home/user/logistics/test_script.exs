alias Logistics.Freight
alias Logistics.Freight.{Carrier, Warehouse, Shipment, Parcel, ShipmentLeg}

# Create a carrier
{:ok, carrier} = Ash.create(Carrier, %{code: "DHL", name: "DHL Express"}, domain: Freight)
IO.puts("Created carrier: #{inspect(carrier.code)}")

# Try creating duplicate live carrier (should fail)
{:error, error} = Ash.create(Carrier, %{code: "DHL", name: "DHL Express 2"}, domain: Freight)
IO.puts("Duplicate carrier error: #{inspect(error)}")

# Try creating carrier with different case (should fail - citext)
{:error, error} = Ash.create(Carrier, %{code: "dhl", name: "DHL Express 3"}, domain: Freight)
IO.puts("Case-insensitive duplicate carrier error: #{inspect(error)}")

# Retire the carrier
{:ok, retired_carrier} = Ash.update(carrier, %{retired_at: DateTime.utc_now()}, domain: Freight)
IO.puts("Retired carrier: #{inspect(retired_carrier.retired_at)}")

# Now create a new carrier with same code (should succeed since old one is retired)
{:ok, carrier2} = Ash.create(Carrier, %{code: "DHL", name: "DHL Express New"}, domain: Freight)
IO.puts("Created carrier with same code after retire: #{inspect(carrier2.code)}")

# Create a warehouse
{:ok, warehouse} = Ash.create(Warehouse, %{code: "WH1", name: "Warehouse 1", region: "East"}, domain: Freight)
IO.puts("Created warehouse: #{inspect(warehouse.code)}")

# Try creating duplicate active warehouse
{:error, error} = Ash.create(Warehouse, %{code: "WH1", name: "Warehouse 2", region: "West"}, domain: Freight)
IO.puts("Duplicate warehouse error: #{inspect(error)}")

# Decommission the warehouse
{:ok, _decommissioned_wh} = Ash.update(warehouse, %{decommissioned: true}, domain: Freight)
IO.puts("Decommissioned warehouse")

# Create new warehouse with same code (should succeed)
{:ok, warehouse2} = Ash.create(Warehouse, %{code: "WH1", name: "Warehouse 3", region: "North"}, domain: Freight)
IO.puts("Created warehouse with same code after decommission: #{inspect(warehouse2.code)}")

# Create a shipment
{:ok, shipment} = Ash.create(Shipment, %{
  reference: "SHIP-001",
  carrier_id: carrier2.id,
  origin_warehouse_id: warehouse2.id,
  declared_value_cents: 1000
}, domain: Freight)
IO.puts("Created shipment: #{inspect(shipment.reference)}")

# Try creating duplicate shipment reference
{:error, error} = Ash.create(Shipment, %{
  reference: "SHIP-001",
  carrier_id: carrier2.id
}, domain: Freight)
IO.puts("Duplicate shipment error: #{inspect(error)}")

# Create a parcel
{:ok, parcel} = Ash.create(Parcel, %{
  tracking_code: "TRACK-001",
  weight_grams: 100,
  shipment_id: shipment.id
}, domain: Freight)
IO.puts("Created parcel: #{inspect(parcel.tracking_code)}")

# Try creating duplicate tracking code
{:error, error} = Ash.create(Parcel, %{
  tracking_code: "TRACK-001",
  weight_grams: 200,
  shipment_id: shipment.id
}, domain: Freight)
IO.puts("Duplicate parcel tracking error: #{inspect(error)}")

# Create a fragile parcel
{:ok, fragile_parcel} = Ash.create(Parcel, %{
  tracking_code: "TRACK-002",
  weight_grams: 200,
  fragile: true,
  shipment_id: shipment.id
}, domain: Freight)
IO.puts("Created fragile parcel: #{inspect(fragile_parcel.tracking_code)}")

# Try creating second fragile parcel for same shipment
{:error, error} = Ash.create(Parcel, %{
  tracking_code: "TRACK-003",
  weight_grams: 300,
  fragile: true,
  shipment_id: shipment.id
}, domain: Freight)
IO.puts("Second fragile parcel error: #{inspect(error)}")

# Create a shipment leg
{:ok, leg} = Ash.create(ShipmentLeg, %{
  shipment_id: shipment.id,
  warehouse_id: warehouse2.id,
  sequence: 1
}, domain: Freight)
IO.puts("Created shipment leg: sequence=#{leg.sequence}")

# Try creating duplicate leg sequence
{:error, error} = Ash.create(ShipmentLeg, %{
  shipment_id: shipment.id,
  warehouse_id: warehouse2.id,
  sequence: 1
}, domain: Freight)
IO.puts("Duplicate leg sequence error: #{inspect(error)}")

# Test destroying carrier with shipments (should fail)
{:error, error} = Ash.destroy(carrier2, domain: Freight)
IO.puts("Destroy carrier with shipments error: #{inspect(error)}")

# Test destroying warehouse with legs (should fail)
{:error, error} = Ash.destroy(warehouse2, domain: Freight)
IO.puts("Destroy warehouse with legs error: #{inspect(error)}")

# Test check constraints
{:error, error} = Ash.create(Warehouse, %{code: "WH2", name: "WH2", region: "South", capacity_parcels: -1}, domain: Freight)
IO.puts("Negative capacity error: #{inspect(error)}")

{:error, error} = Ash.create(Parcel, %{tracking_code: "TRACK-004", weight_grams: 0, shipment_id: shipment.id}, domain: Freight)
IO.puts("Zero weight error: #{inspect(error)}")

{:error, error} = Ash.create(ShipmentLeg, %{shipment_id: shipment.id, warehouse_id: warehouse2.id, sequence: 0}, domain: Freight)
IO.puts("Sequence zero error: #{inspect(error)}")

# Test intake action
{:ok, intake_shipment} = Ash.create(Shipment, :intake, %{
  reference: "SHIP-INTAKE",
  carrier_id: carrier2.id,
  parcels: [
    %{tracking_code: "TRACK-IN-1", weight_grams: 500},
    %{tracking_code: "TRACK-IN-2", weight_grams: 300}
  ]
}, domain: Freight)
IO.puts("Intake shipment created: #{inspect(intake_shipment.reference)}")

# Load parcels
loaded = Ash.load!(intake_shipment, :parcels, domain: Freight)
IO.puts("Intake parcels count: #{length(loaded.parcels)}")

# Test aggregates
{:ok, [shipment_with_aggs]} = Ash.read(Shipment, filter: [reference: "SHIP-001"], load: [:parcel_count, :total_weight_grams], domain: Freight)
IO.puts("Shipment parcel_count: #{shipment_with_aggs.parcel_count}, total_weight: #{shipment_with_aggs.total_weight_grams}")

# Test calculations
{:ok, [_heavy_shipment]} = Ash.read(Shipment, filter: [heavy?: true], load: [:parcel_count], domain: Freight)
IO.puts("Heavy shipment filter test passed")

# Test reading carriers - retired ones should not appear
{:ok, carriers} = Ash.read(Carrier, domain: Freight)
IO.puts("Visible carriers count: #{length(carriers)} (should be 1 - only the unretired one)")

IO.puts("\nAll tests passed!")
