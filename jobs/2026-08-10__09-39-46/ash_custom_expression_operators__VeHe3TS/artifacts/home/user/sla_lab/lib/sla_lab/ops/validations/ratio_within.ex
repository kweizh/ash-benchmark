defmodule SlaLab.Ops.Validations.RatioWithin do
  use Ash.Resource.Validation

  alias Ash.Error.Changes.InvalidAttribute
  import Ash.Expr

  @impl true
  def init(opts) do
    max_bps = Keyword.get(opts, :max_bps)

    if is_integer(max_bps) && max_bps > 0 do
      {:ok, [max_bps: max_bps]}
    else
      {:error, "max_bps must be a positive integer"}
    end
  end

  @impl true
  def atomic(_changeset, opts, _context) do
    max_bps = opts[:max_bps]

    [
      {:atomic, [:actual_hours],
       expr(
         not is_nil(^atomic_ref(:actual_hours)) and
           ratio_bps(^atomic_ref(:actual_hours), ^atomic_ref(:promised_hours)) > ^max_bps
       ),
       expr(
         error(^InvalidAttribute, %{
           field: :actual_hours,
           value: ^atomic_ref(:actual_hours),
           message: "delivery ratio exceeds the allowed maximum"
         })
       )}
    ]
  end
end
