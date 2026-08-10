defmodule SlaLab.Ops do
  use Ash.Domain, otp_app: :sla_lab

  resources do
    resource SlaLab.Ops.Carrier

    resource SlaLab.Ops.Shipment do
      define :shipments_on_route, action: :on_route, args: [:route]
    end
  end
end
