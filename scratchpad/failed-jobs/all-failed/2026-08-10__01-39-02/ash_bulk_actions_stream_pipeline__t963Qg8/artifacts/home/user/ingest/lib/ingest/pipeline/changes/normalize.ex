defmodule Ingest.Pipeline.Changes.Normalize do
  use Ash.Resource.Change

  def change(changeset, _opts, _context) do
    meter_code = Ash.Changeset.get_attribute(changeset, :meter_code) || changeset.data.meter_code
    raw_kwh = Ash.Changeset.get_attribute(changeset, :raw_kwh) || changeset.data.raw_kwh

    case Ash.get(Ingest.Pipeline.Meter, meter_code) do
      {:ok, %{active: true, scale_bp: scale_bp}} ->
        net_kwh = div(raw_kwh * scale_bp + 5000, 10_000)

        changeset
        |> Ash.Changeset.change_attribute(:net_kwh, net_kwh)
        |> Ash.Changeset.change_attribute(:status, :normalized)

      _ ->
        changeset
        |> Ash.Changeset.change_attribute(:status, :rejected)
    end
  end
end
