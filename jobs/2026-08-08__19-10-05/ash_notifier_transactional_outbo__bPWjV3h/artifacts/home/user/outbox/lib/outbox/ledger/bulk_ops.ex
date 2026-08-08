defmodule Outbox.Ledger.BulkOps do
  @moduledoc """
  Batch entry points for ledger operations that produce exactly one
  outbox entry per written record.
  """

  @doc """
  Creates every account in `inputs` with a single Ash batch create.
  Returns `{:ok, [Outbox.Ledger.Account.t()]}`.
  """
  def open_many(inputs) do
    Ash.bulk_create(inputs, Outbox.Ledger.Account, :open,
      domain: Outbox.Ledger,
      authorize?: false,
      return_records?: true
    )
    |> case do
      %Ash.BulkResult{status: :success, records: records} ->
        {:ok, records}

      %Ash.BulkResult{status: :error, errors: errors} ->
        {:error, errors}
    end
  end

  @doc """
  Applies the `:freeze` action to every given account with a single Ash batch update.
  Returns `{:ok, [Outbox.Ledger.Account.t()]}`.
  """
  def freeze_many(accounts) do
    Ash.bulk_update(accounts, :freeze, %{},
      domain: Outbox.Ledger,
      authorize?: false,
      return_records?: true
    )
    |> case do
      %Ash.BulkResult{status: :success, records: records} ->
        {:ok, records}

      %Ash.BulkResult{status: :error, errors: errors} ->
        {:error, errors}
    end
  end
end
