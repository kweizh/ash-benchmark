defmodule Outbox.Ledger.SufficientFunds do
  @moduledoc """
  Rejects a withdrawal that is not positive or that would overdraw the account.
  """

  use Ash.Resource.Validation

  @impl true
  def validate(changeset, _opts, _context) do
    amount = Ash.Changeset.get_argument(changeset, :amount)

    cond do
      not is_integer(amount) or amount <= 0 ->
        {:error,
         Ash.Error.Changes.InvalidArgument.exception(
           field: :amount,
           message: "must be positive"
         )}

      amount > changeset.data.balance ->
        {:error,
         Ash.Error.Changes.InvalidArgument.exception(
           field: :amount,
           message: "insufficient funds"
         )}

      true ->
        :ok
    end
  end
end
