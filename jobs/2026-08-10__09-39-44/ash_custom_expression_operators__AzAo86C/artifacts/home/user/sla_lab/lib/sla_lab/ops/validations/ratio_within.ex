defmodule SlaLab.Ops.Validations.RatioWithin do
  @moduledoc """
  A validation that rejects an update when the ratio in basis points of the new
  `actual_hours` over the record's `promised_hours` exceeds the configured
  maximum.

  Placed on an action with the option `max_bps: <integer>`.  The check is
  performed atomically so it works for single updates as well as for
  `Ash.bulk_update/4` with `strategy: [:atomic]`.
  """

  use Ash.Resource.Validation
  import Ash.Expr
  alias Ash.Error.Changes.InvalidAttribute

  @impl Ash.Resource.Validation
  def atomic(_changeset, opts, _context) do
    max_bps = opts[:max_bps]

    condition_expr =
      expr(
        ratio_bps(atomic_ref(:actual_hours), atomic_ref(:promised_hours)) > ^max_bps
      )

    error_expr =
      expr(
        error(^InvalidAttribute, %{
          field: :actual_hours,
          message: "delivery ratio exceeds the allowed maximum"
        })
      )

    {:atomic, [:actual_hours], condition_expr, error_expr}
  end
end
