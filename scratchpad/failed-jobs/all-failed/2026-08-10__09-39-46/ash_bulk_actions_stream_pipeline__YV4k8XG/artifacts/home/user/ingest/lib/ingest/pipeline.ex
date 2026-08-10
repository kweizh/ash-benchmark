defmodule Ingest.Pipeline do
  use Ash.Domain, otp_app: :ingest

  resources do
    resource Ingest.Pipeline.Meter
    resource Ingest.Pipeline.Reading
    resource Ingest.Pipeline.MeterRollup
  end
end
