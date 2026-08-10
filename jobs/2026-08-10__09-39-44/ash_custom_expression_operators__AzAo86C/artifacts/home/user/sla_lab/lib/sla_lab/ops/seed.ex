defmodule SlaLab.Ops.Seed do
  @moduledoc """
  Deterministic fixture data for the SLA lab.

  DO NOT MODIFY THIS FILE. The verification suite depends on the exact data
  produced here.
  """

  @carriers [
    %{code: "NORDIC", tier: :gold},
    %{code: "PACIFIC", tier: :silver},
    %{code: "ARCTIC", tier: :bronze}
  ]

  # {reference, carrier_code, origin_zone, destination_zone, promised_hours,
  #  actual_hours, priority}
  @shipments [
    {"S01", "NORDIC", "ams", "jfk", 48, 24, :standard},
    {"S02", "NORDIC", "jfk", "ams", 48, 96, :express},
    {"S03", "NORDIC", "ams", "lhr", 24, nil, :critical},
    {"S04", "NORDIC", "lhr", "ams", 32, 1, :standard},
    {"S05", "PACIFIC", "sin", "hkg", 12, 18, :standard},
    {"S06", "PACIFIC", "hkg", "sin", 12, 12, :standard},
    {"S07", "PACIFIC", "sin", "nrt", 32, 3, :express},
    {"S08", "ARCTIC", "ams", "osl", 10, nil, :standard},
    {"S09", "ARCTIC", "osl", "ams", 10, nil, :standard},
    {"S10", "NORDIC", "cdg", "ams", 8, 40, :standard}
  ]

  @doc """
  Inserts the fixture data and returns
  `%{carriers: %{code => record}, shipments: %{reference => record}}`.
  """
  def seed! do
    carriers =
      Map.new(@carriers, fn attrs ->
        {attrs.code, Ash.create!(SlaLab.Ops.Carrier, attrs, authorize?: false)}
      end)

    shipments =
      Map.new(@shipments, fn {reference, carrier_code, origin, destination, promised, actual,
                              priority} ->
        record =
          Ash.create!(
            SlaLab.Ops.Shipment,
            %{
              reference: reference,
              origin_zone: origin,
              destination_zone: destination,
              promised_hours: promised,
              actual_hours: actual,
              priority: priority,
              carrier_id: carriers[carrier_code].id
            },
            authorize?: false
          )

        {reference, record}
      end)

    %{carriers: carriers, shipments: shipments}
  end
end
