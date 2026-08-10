defmodule SlaLab.Ops.Validations.RatioWithin do
  @moduledoc """
  Validates that the delivery ratio (in basis points, see
  `SlaLab.Expressions.RatioBps`) of the incoming `actual_hours` value over
  the record's `promised_hours` does not exceed a configured maximum.

  ## Options

    * `:max_bps` - the maximum allowed ratio, in basis points.
  """

  use Ash.Resource.Validation

  alias Ash.Error.Changes.InvalidAttribute
  alias SlaLab.Expressions.RatioBps

  @impl true
  def init(opts) do
    if is_integer(opts[:max_bps]) do
      {:ok, opts}
    else
      {:error, "max_bps must be provided as an integer"}
    end
  end

  @impl true
  def validate(changeset, opts, _context) do
    actual_hours = Ash.Changeset.get_attribute(changeset, :actual_hours)
    promised_hours = Ash.Changeset.get_attribute(changeset, :promised_hours)
    max_bps = opts[:max_bps]

    case RatioBps.ratio_bps(actual_hours, promised_hours) do
      ratio when is_integer(ratio) and ratio > max_bps ->
        {:error, field: :actual_hours, message: "delivery ratio exceeds the allowed maximum"}

      _ ->
        :ok
    end
  end

  @impl true
  def atomic(_changeset, opts, _context) do
    max_bps = opts[:max_bps]

    {:atomic, [:actual_hours],
     expr(ratio_bps(^atomic_ref(:actual_hours), promised_hours) > ^max_bps),
     expr(
       error(^InvalidAttribute, %{
         field: :actual_hours,
         value: ^atomic_ref(:actual_hours),
         message: "delivery ratio exceeds the allowed maximum"
       })
     )}
  end
end
