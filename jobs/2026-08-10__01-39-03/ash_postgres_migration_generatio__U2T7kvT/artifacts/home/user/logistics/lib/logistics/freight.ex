defmodule Logistics.Freight do
  use Ash.Domain, otp_app: :logistics

  resources do
    resource Logistics.Freight.Carrier
    resource Logistics.Freight.Warehouse
    resource Logistics.Freight.Shipment
    resource Logistics.Freight.Parcel
    resource Logistics.Freight.ShipmentLeg
  end
end
