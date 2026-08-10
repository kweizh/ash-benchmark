defmodule SlaLab.Ops.Validations.RatioWithin do
  use Ash.Resource.Validation

  @impl true
  def init(opts) do
    if is_integer(opts[:max_bps]) do
      {:ok, opts}
    else
      {:error, "max_bps must be an integer"}
    end
  end

  @impl true
  def validate(changeset, opts, _context) do
    actual_hours = Ash.Changeset.get_attribute(changeset, :actual_hours)
    promised_hours = Ash.Changeset.get_attribute(changeset, :promised_hours) || changeset.data.promised_hours
    max_bps = opts[:max_bps]

    ratio = SlaLab.Expressions.RatioBps.ratio_bps(actual_hours, promised_hours)

    if ratio && ratio > max_bps do
      {:error, Ash.Error.Changes.InvalidAttribute.exception(
        field: :actual_hours,
        value: actual_hours,
        message: "delivery ratio exceeds the allowed maximum"
      )}
    else
      :ok
    end
  end

  @impl true
  def atomic(_changeset, opts, _context) do
    import Ash.Expr
    max_bps = opts[:max_bps]
    {:atomic, [:actual_hours],
     expr(ratio_bps(^atomic_ref(:actual_hours), promised_hours) > ^max_bps),
     expr(
       error(
         Ash.Error.Changes.InvalidAttribute,
         %{
           field: :actual_hours,
           value: ^atomic_ref(:actual_hours),
           message: "delivery ratio exceeds the allowed maximum"
         }
       )
     )}
  end
end
