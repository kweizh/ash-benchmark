defmodule Ingest.Pipeline.Ingestion do
  require Ash.Query

  def ingest(rows, batch_ref, opts \\ []) do
    batch_size = Keyword.get(opts, :batch_size, 100)

    # 1. Validate rows and categorize failed ones
    validated_rows = validate_rows(rows)

    # 2. Filter out failed rows to find sound rows
    sound_rows = Enum.filter(validated_rows, &(elem(&1, 0) == :ok))

    # 3. Find which sound rows are already stored (skipped)
    sound_ids = Enum.map(sound_rows, fn {:ok, %{row: %{external_id: id}}} -> id end)

    existing_ids =
      if sound_ids == [] do
        MapSet.new()
      else
        page =
          Ingest.Pipeline.Reading
          |> Ash.Query.filter(external_id in ^sound_ids)
          |> Ash.read!()

        page.results
        |> Enum.map(& &1.external_id)
        |> MapSet.new()
      end

    # 4. Categorize sound rows into skipped and inserted
    skipped_count =
      Enum.count(sound_rows, fn {:ok, %{row: %{external_id: id}}} ->
        MapSet.member?(existing_ids, id)
      end)

    inserted_rows =
      Enum.reject(sound_rows, fn {:ok, %{row: %{external_id: id}}} ->
        MapSet.member?(existing_ids, id)
      end)

    inserted_count = length(inserted_rows)

    # 5. Prepare and write inserted rows in batches
    bulk_inputs =
      Enum.map(inserted_rows, fn {:ok, %{row: row}} ->
        Map.put(row, :batch_ref, batch_ref)
      end)

    if bulk_inputs != [] do
      Ash.bulk_create!(bulk_inputs, Ingest.Pipeline.Reading, :ingest,
        batch_size: batch_size,
        return_records?: true,
        sorted?: true
      )
    end

    inserted_external_ids =
      Enum.map(inserted_rows, fn {:ok, %{row: %{external_id: id}}} -> id end)

    failed_list =
      validated_rows
      |> Enum.filter(&(elem(&1, 0) == :failed))
      |> Enum.map(&elem(&1, 1))

    status =
      cond do
        failed_list == [] ->
          :success

        inserted_count == 0 ->
          :error

        true ->
          :partial_success
      end

    %{
      batch_ref: batch_ref,
      status: status,
      inserted: inserted_count,
      skipped: skipped_count,
      failed: failed_list,
      inserted_external_ids: inserted_external_ids
    }
  end

  def ingest_stream(rows, batch_ref, opts \\ []) do
    batch_size = Keyword.get(opts, :batch_size, 100)

    rows
    |> Stream.with_index()
    |> Stream.chunk_every(batch_size)
    |> Stream.flat_map(fn chunk ->
      Enum.map(chunk, fn {row, index} ->
        params = Map.put(row, :batch_ref, batch_ref)
        changeset = Ash.Changeset.for_create(Ingest.Pipeline.Reading, :ingest, params)

        case Ash.create(changeset) do
          {:ok, reading} ->
            {:ok, reading}

          {:error, _error} ->
            {:error, index}
        end
      end)
    end)
  end

  def pending_stream(opts \\ []) do
    batch_size = Keyword.get(opts, :batch_size, 500)

    Ingest.Pipeline.Reading
    |> Ash.Query.filter(status == :pending)
    |> Ash.stream!(batch_size: batch_size)
  end

  def reconcile(batch_ref) do
    # 1. Normalize pending readings of the batch
    pending_query =
      Ingest.Pipeline.Reading
      |> Ash.Query.filter(batch_ref == ^batch_ref and status == :pending)

    normalize_result =
      Ash.bulk_update!(pending_query, :normalize, %{},
        strategy: [:stream],
        return_records?: true
      )

    normalized_records = normalize_result.records || []
    count_normalized = Enum.count(normalized_records, &(&1.status == :normalized))
    count_rejected = Enum.count(normalized_records, &(&1.status == :rejected))

    # 2. Accept normalized readings of the batch
    normalized_query =
      Ingest.Pipeline.Reading
      |> Ash.Query.filter(batch_ref == ^batch_ref and status == :normalized)

    accept_result =
      Ash.bulk_update!(normalized_query, :accept, %{},
        strategy: [:atomic],
        return_records?: true
      )

    accepted_records = accept_result.records || []
    count_accepted = length(accepted_records)

    # 3. Update the MeterRollup rows
    accepted_records
    |> Enum.group_by(& &1.meter_code)
    |> Enum.each(fn {meter_code, readings} ->
      sum_net_kwh = readings |> Enum.map(& &1.net_kwh) |> Enum.sum()
      count_readings = length(readings)

      case Ash.get(Ingest.Pipeline.MeterRollup, meter_code) do
        {:ok, rollup} ->
          rollup
          |> Ash.Changeset.for_update(:update, %{
            total_net_kwh: rollup.total_net_kwh + sum_net_kwh,
            reading_count: rollup.reading_count + count_readings,
            last_batch_ref: batch_ref,
            revision: rollup.revision + 1
          })
          |> Ash.update!()

        {:error, _} ->
          Ingest.Pipeline.MeterRollup
          |> Ash.Changeset.for_create(:create, %{
            meter_code: meter_code,
            total_net_kwh: sum_net_kwh,
            reading_count: count_readings,
            last_batch_ref: batch_ref,
            revision: 1
          })
          |> Ash.create!()
      end
    end)

    %{
      batch_ref: batch_ref,
      normalized: count_normalized,
      rejected: count_rejected,
      accepted: count_accepted
    }
  end

  def purge_rejected(batch_ref) do
    rejected_query =
      Ingest.Pipeline.Reading
      |> Ash.Query.filter(batch_ref == ^batch_ref and status == :rejected)

    destroy_result =
      Ash.bulk_destroy!(rejected_query, :destroy, %{}, return_records?: true)

    length(destroy_result.records || [])
  end

  # Helper to validate rows and categorize failed ones
  defp validate_rows(rows) do
    {validated_rows, _seen_ids} =
      rows
      |> Enum.with_index()
      |> Enum.reduce({[], MapSet.new()}, fn {row, index}, {acc, seen_ids} ->
        external_id = Map.get(row, :external_id)

        has_missing_field =
          is_nil(external_id) or
            is_nil(Map.get(row, :meter_code)) or
            is_nil(Map.get(row, :raw_kwh)) or
            is_nil(Map.get(row, :recorded_on))

        raw_kwh = Map.get(row, :raw_kwh)

        cond do
          # 1. Missing field check
          has_missing_field ->
            failed_info = %{index: index, external_id: external_id, reason: :missing_field}

            new_seen_ids =
              if external_id != nil, do: MapSet.put(seen_ids, external_id), else: seen_ids

            {[{:failed, failed_info} | acc], new_seen_ids}

          # 2. Negative raw_kwh check
          raw_kwh < 0 ->
            failed_info = %{index: index, external_id: external_id, reason: :negative_raw_kwh}

            new_seen_ids =
              if external_id != nil, do: MapSet.put(seen_ids, external_id), else: seen_ids

            {[{:failed, failed_info} | acc], new_seen_ids}

          # 3. Duplicate in batch check
          MapSet.member?(seen_ids, external_id) ->
            failed_info = %{index: index, external_id: external_id, reason: :duplicate_in_batch}
            {[{:failed, failed_info} | acc], seen_ids}

          # Otherwise, the row is sound!
          true ->
            new_seen_ids = MapSet.put(seen_ids, external_id)
            {[{:ok, %{index: index, row: row}} | acc], new_seen_ids}
        end
      end)

    Enum.reverse(validated_rows)
  end
end
