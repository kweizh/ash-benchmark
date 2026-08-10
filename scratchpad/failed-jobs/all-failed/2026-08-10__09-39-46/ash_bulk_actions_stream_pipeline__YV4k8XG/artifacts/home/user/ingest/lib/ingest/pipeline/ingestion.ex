defmodule Ingest.Pipeline.Ingestion do
  @moduledoc """
  The delivery pipeline for ingesting meter readings, reconciling them, and maintaining rollups.
  """

  require Ash.Query

  @required_keys [:external_id, :meter_code, :raw_kwh, :recorded_on]

  @doc """
  Eagerly ingests a list of reading rows for a given batch.

  Returns a map with keys: `:batch_ref`, `:status`, `:inserted`, `:skipped`, `:failed`,
  and `:inserted_external_ids`.
  """
  def ingest(rows, batch_ref, opts \\ []) do
    batch_size = Keyword.get(opts, :batch_size, 100)

    {failed, valid_rows} = validate_and_dedup_rows(rows)

    # Check which external_ids already exist in the store
    existing_ids = existing_external_ids(valid_rows)

    # Separate skipped vs to-be-inserted
    {skipped_rows, to_insert} =
      valid_rows
      |> Enum.split_with(fn row -> MapSet.member?(existing_ids, row.external_id) end)

    skipped = length(skipped_rows)

    # Insert in batches, maintaining input order
    inserted_external_ids =
      to_insert
      |> Enum.chunk_every(batch_size)
      |> Enum.flat_map(fn batch ->
        inputs =
          Enum.map(batch, fn row ->
            %{
              external_id: row.external_id,
              meter_code: row.meter_code,
              raw_kwh: row.raw_kwh,
              recorded_on: row.recorded_on,
              batch_ref: batch_ref
            }
          end)

        result = Ash.bulk_create!(inputs, Ingest.Pipeline.Reading, :ingest,
          return_records?: true,
          return_errors?: true,
          stop_on_error?: false
        )

        result.records |> Enum.map(& &1.external_id)
      end)

    inserted = length(inserted_external_ids)

    status =
      cond do
        failed == [] && inserted > 0 -> :success
        failed == [] && inserted == 0 -> :success
        failed != [] && inserted == 0 -> :error
        true -> :partial_success
      end

    %{
      batch_ref: batch_ref,
      status: status,
      inserted: inserted,
      skipped: skipped,
      failed: failed,
      inserted_external_ids: inserted_external_ids
    }
  end

  @doc """
  Lazily ingests a list of reading rows for a given batch. No duplicate suppression.

  Returns an enumerable that yields `{:ok, reading}` or `{:error, index}` tuples.
  """
  def ingest_stream(rows, batch_ref, opts \\ []) do
    batch_size = Keyword.get(opts, :batch_size, 100)

    rows_with_index = Enum.with_index(rows)

    rows_with_index
    |> Stream.chunk_every(batch_size)
    |> Stream.flat_map(fn chunk ->
      chunk
      |> Enum.map(fn {row, idx} ->
        input = %{
          external_id: row[:external_id],
          meter_code: row[:meter_code],
          raw_kwh: row[:raw_kwh],
          recorded_on: row[:recorded_on],
          batch_ref: batch_ref
        }

        case Ash.Changeset.for_create(Ingest.Pipeline.Reading, :ingest, input)
             |> Ash.create() do
          {:ok, reading} -> {:ok, reading}
          {:error, _error} -> {:error, idx}
        end
      end)
    end)
  end

  @doc """
  Returns a lazy enumerable of Reading records whose status is `:pending`.

  Uses keyset pagination with configurable batch_size (default 500).
  """
  def pending_stream(opts \\ []) do
    batch_size = Keyword.get(opts, :batch_size, 500)

    Stream.resource(
      fn -> nil end,
      fn
        false ->
          {:halt, nil}

        after_keyset ->
          query =
            Ingest.Pipeline.Reading
            |> Ash.Query.filter(status: :pending)
            |> Ash.Query.sort(:external_id)

          keyset = if after_keyset != nil, do: [after: after_keyset], else: []
          page_opts = Keyword.merge(keyset, limit: batch_size)

          case Ash.read!(query, page: page_opts) do
            %{more?: true, results: results} ->
              {results, List.last(results).__metadata__.keyset}

            %{results: results} ->
              {results, false}
          end
      end,
      & &1
    )
  end

  @doc """
  Runs one reconciliation pass over the readings of a specific delivery (batch_ref).

  Returns a map with keys: `:batch_ref`, `:normalized`, `:rejected`, `:accepted`.
  """
  def reconcile(batch_ref) do
    # Step 1: Normalize all pending readings for this batch
    pending_query =
      Ingest.Pipeline.Reading
      |> Ash.Query.filter(status: :pending, batch_ref: batch_ref)

    normalize_result =
      Ash.bulk_update!(pending_query, :normalize, %{},
        return_records?: true,
        return_errors?: true,
        strategy: [:stream]
      )

    normalized_count =
      normalize_result.records
      |> Enum.count(fn r -> r.status == :normalized end)

    rejected_count =
      normalize_result.records
      |> Enum.count(fn r -> r.status == :rejected end)

    # Step 2: Accept all normalized readings for this batch
    normalized_query =
      Ingest.Pipeline.Reading
      |> Ash.Query.filter(status: :normalized, batch_ref: batch_ref)

    accept_result =
      Ash.bulk_update!(normalized_query, :accept, %{},
        return_records?: true,
        return_errors?: true
      )

    accepted_count = length(accept_result.records)

    # Step 3: Update rollups for each meter that gained accepted readings
    if accepted_count > 0 do
      accepted_readings = accept_result.records

      # Group by meter_code
      by_meter = Enum.group_by(accepted_readings, & &1.meter_code)

      Enum.each(by_meter, fn {meter_code, readings} ->
        total_net = Enum.sum(Enum.map(readings, & &1.net_kwh))
        count = length(readings)

        # Find or create the rollup
        existing =
          Ingest.Pipeline.MeterRollup
          |> Ash.Query.filter(meter_code: meter_code)
          |> Ash.read!()
          |> List.first()

        if existing do
          # Update existing rollup
          existing
          |> Ash.Changeset.for_update(:update, %{
            total_net_kwh: existing.total_net_kwh + total_net,
            reading_count: existing.reading_count + count,
            revision: existing.revision + 1,
            last_batch_ref: batch_ref
          })
          |> Ash.update!()
        else
          # Create new rollup
          Ingest.Pipeline.MeterRollup
          |> Ash.Changeset.for_create(:create, %{
            meter_code: meter_code,
            total_net_kwh: total_net,
            reading_count: count,
            revision: 1,
            last_batch_ref: batch_ref
          })
          |> Ash.create!()
        end
      end)
    end

    %{
      batch_ref: batch_ref,
      normalized: normalized_count,
      rejected: rejected_count,
      accepted: accepted_count
    }
  end

  @doc """
  Destroys every `:rejected` reading of the given delivery and returns the count destroyed.
  """
  def purge_rejected(batch_ref) do
    query =
      Ingest.Pipeline.Reading
      |> Ash.Query.filter(status: :rejected, batch_ref: batch_ref)

    result =
      Ash.bulk_destroy!(query, :destroy, %{},
        return_records?: true,
        return_errors?: true
      )

    length(result.records)
  end

  # Private helpers

  defp validate_and_dedup_rows(rows) do
    rows_with_index = Enum.with_index(rows)

    # First pass: identify failures and track seen external_ids
    {failed, valid_with_idx, _seen} =
      Enum.reduce(rows_with_index, {[], [], MapSet.new()}, fn {row, idx}, {failed, valid, seen} ->
        case validate_row(row, idx, seen) do
          {:ok, clean_row, new_seen} ->
            {failed, [{clean_row, idx} | valid], new_seen}

          {:error, failure} ->
            {[failure | failed], valid, seen}
        end
      end)

    # Reverse to restore original order (we prepended during reduce)
    failed = Enum.reverse(failed)
    valid_with_idx = Enum.reverse(valid_with_idx)

    # Sort valid rows by original index to maintain input order
    valid_with_idx = Enum.sort_by(valid_with_idx, fn {_row, idx} -> idx end)
    valid_rows = Enum.map(valid_with_idx, fn {row, _idx} -> row end)

    {failed, valid_rows}
  end

  defp validate_row(row, idx, seen) do
    # Check missing fields
    missing =
      Enum.find(@required_keys, fn key ->
        value = Map.get(row, key)
        is_nil(value)
      end)

    if missing do
      {:error,
       %{
         index: idx,
         external_id: Map.get(row, :external_id),
         reason: :missing_field
       }}
    else
      # Check negative raw_kwh
      if row.raw_kwh < 0 do
        {:error,
         %{
           index: idx,
           external_id: row.external_id,
           reason: :negative_raw_kwh
         }}
      else
        # Check duplicate in batch
        ext_id = row.external_id

        if MapSet.member?(seen, ext_id) do
          {:error,
           %{
             index: idx,
             external_id: ext_id,
             reason: :duplicate_in_batch
           }}
        else
          {:ok, row, MapSet.put(seen, ext_id)}
        end
      end
    end
  end

  defp existing_external_ids(rows) do
    external_ids = Enum.map(rows, & &1.external_id)

    if external_ids == [] do
      MapSet.new()
    else
      Ingest.Pipeline.Reading
      |> Ash.Query.filter(external_id in ^external_ids)
      |> Ash.read!()
      |> Enum.map(& &1.external_id)
      |> MapSet.new()
    end
  end
end
