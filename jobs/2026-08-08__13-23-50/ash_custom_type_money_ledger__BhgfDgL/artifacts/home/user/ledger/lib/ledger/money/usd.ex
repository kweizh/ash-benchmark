defmodule Ledger.Money.Usd do
  @moduledoc """
  A `Ledger.Money.Type` narrowed to USD only, bounded inclusively between
  `USD 0.00` and `USD 10000.00`.
  """

  use Ash.Type.NewType,
    subtype_of: Ledger.Money.Type,
    constraints: [
      currencies: [:usd],
      min: "USD 0.00",
      max: "USD 10000.00"
    ]
end
