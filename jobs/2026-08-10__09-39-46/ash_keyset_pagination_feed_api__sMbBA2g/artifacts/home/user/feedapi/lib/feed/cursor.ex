defmodule Feed.Cursor do
  @moduledoc """
  An opaque, tamper-evident cursor codec for keyset-based pagination.

  Cursors are encoded using URL-safe Base64 and include a checksum to detect
  tampering or forgery.
  """

  @salt "feed_cursor_v1"

  @doc """
  Encodes a payload map into a tamper-evident cursor string.

  The payload must have exactly the keys:
    - `:feed` — an atom identifying the feed
    - `:direction` — `:next` or `:prev`
    - `:keyset` — a UTF-8 binary (the Ash keyset value)

  Returns a URL-safe Base64 string matching `~r/\\A[A-Za-z0-9_-]+\\z/`.
  Encoding the same map twice produces the same string.
  """
  @spec encode(%{feed: atom(), direction: :next | :prev, keyset: String.t()}) :: String.t()
  def encode(%{feed: feed, direction: direction, keyset: keyset})
      when is_atom(feed) and direction in [:next, :prev] and is_binary(keyset) do
    payload = %{feed: feed, direction: direction, keyset: keyset}
    serialized = :erlang.term_to_binary(payload)
    checksum = compute_checksum(serialized)
    serialized <> checksum |> Base.url_encode64(padding: false)
  end

  @doc """
  Decodes a cursor string back into a payload map.

  Returns `{:ok, %{feed: atom, direction: :next | :prev, keyset: binary}}`
  for a valid cursor produced by `encode/1`.

  Returns `{:error, :invalid_cursor}` for anything else, including:
    - Arbitrary strings
    - Cursors with characters removed or changed
    - Hand-assembled payloads that did not go through `encode/1`
  """
  @spec decode(String.t()) ::
          {:ok, %{feed: atom(), direction: :next | :prev, keyset: String.t()}}
          | {:error, :invalid_cursor}
  def decode(cursor) when is_binary(cursor) do
    with {:ok, decoded} <- Base.url_decode64(cursor, padding: false),
         true <- byte_size(decoded) > 4,
         serialized_size = byte_size(decoded) - 4,
         <<serialized::binary-size(serialized_size), checksum::binary-size(4)>> <- decoded,
         ^checksum <- compute_checksum(serialized),
         {:ok, payload} <- safe_decode(serialized),
         true <- valid_payload?(payload) do
      {:ok, payload}
    else
      _ -> {:error, :invalid_cursor}
    end
  end

  def decode(_), do: {:error, :invalid_cursor}

  defp compute_checksum(data) do
    :crypto.hash(:sha256, @salt <> data) |> binary_part(0, 4)
  end

  defp safe_decode(binary) do
    {:ok, :erlang.binary_to_term(binary, [:safe])}
  rescue
    _ -> :error
  end

  defp valid_payload?(payload) when is_map(payload) do
    map_size(payload) == 3 and
      is_map_key(payload, :feed) and is_atom(payload.feed) and
      is_map_key(payload, :direction) and payload.direction in [:next, :prev] and
      is_map_key(payload, :keyset) and is_binary(payload.keyset)
  end

  defp valid_payload?(_), do: false
end
