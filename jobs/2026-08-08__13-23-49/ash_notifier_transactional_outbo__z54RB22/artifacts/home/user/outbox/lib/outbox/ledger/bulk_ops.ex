defmodule Outbox.Ledger.BulkOps do
  @moduledoc """
  Bulk operations on Ledger resources.
  """

  def open_many(inputs) do
    case Ash.bulk_create(inputs, Outbox.Ledger.Account, :open, return_records?: true, notify?: true) do
      %Ash.BulkResult{status: status, records: records} when status in [:success, :partial_success] ->
        {:ok, records || []}

      %Ash.BulkResult{status: :error, errors: _errors} ->
        {:ok, []}
    end
  end

  def freeze_many(accounts) do
    case Ash.bulk_update(accounts, :freeze, %{}, return_records?: true, notify?: true) do
      %Ash.BulkResult{status: status, records: records} when status in [:success, :partial_success] ->
        {:ok, records || []}

      %Ash.BulkResult{status: :error, errors: _errors} ->
        {:ok, []}
    end
  end
end
