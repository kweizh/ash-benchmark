defmodule Feed.Cursor do
  @moduledoc """
  An opaque, tamper-evident cursor codec for paginated feeds.

  Each cursor encodes a map with the keys `:feed`, `:direction` and `:keyset`
  together with a HMAC-SHA256 signature so that any tampering or corruption
  is detected on decode.
  """

  @hmac_key <<
    0xFE,
    0xED,
    0xF0,
    0x0D,
    0xBA,
    0xDC,
    0x0F,
    0xFE,
    0xEB,
    0xAD,
    0xC0,
    0xFF,
    0xEE,
    0x11,
    0x22,
    0x33,
    0x44,
    0x55,
    0x66,
    0x77,
    0x88,
    0x99,
    0xAA,
    0xBB,
    0xCC,
    0xDD,
    0xEE,
    0xFF,
    0x00,
    0x11,
    0x22
  >>

  import Bitwise

  @hmac_size 32
  @version 1

  @type payload :: %{
          feed: atom(),
          direction: :next | :prev,
          keyset: String.t()
        }

  @doc """
  Encodes a cursor payload into a URL-safe Base64 string.

  The payload must be a map with exactly the keys `:feed` (an atom),
  `:direction` (`:next` or `:prev`) and `:keyset` (a UTF-8 binary).

  Encoding the same payload twice always produces the same string.
  """
  @spec encode(payload()) :: String.t()
  def encode(%{feed: feed, direction: direction, keyset: keyset})
      when is_atom(feed) and is_atom(direction) and is_binary(keyset) do
    payload = serialize(feed, direction, keyset)
    mac = compute_hmac(payload)
    Base.url_encode64(payload <> mac, padding: false)
  end

  @doc """
  Decodes a cursor string produced by `encode/1`.

  Returns `{:ok, payload}` with exactly the keys `:feed`, `:direction` and
  `:keyset` for a valid cursor, and `{:error, :invalid_cursor}` for anything
  else.  Never raises.
  """
  @spec decode(binary()) :: {:ok, payload()} | {:error, :invalid_cursor}
  def decode(input) when is_binary(input) do
    with {:ok, decoded} <- safe_url_decode64(input),
         true <- byte_size(decoded) > @hmac_size,
         <<payload::binary-size(byte_size(decoded) - @hmac_size),
           mac::binary-size(@hmac_size)>> <- decoded,
         true <- secure_compare(mac, compute_hmac(payload)),
         {:ok, result} <- deserialize(payload) do
      {:ok, result}
    else
      _ -> {:error, :invalid_cursor}
    end
  end

  def decode(_), do: {:error, :invalid_cursor}

  # ---------------------------------------------------------------------------
  # Serialization
  # ---------------------------------------------------------------------------

  defp serialize(feed, direction, keyset) do
    feed_str = Atom.to_string(feed)
    dir_str = Atom.to_string(direction)

    <<
      @version,
      byte_size(feed_str)::32-big,
      feed_str::binary,
      byte_size(dir_str)::32-big,
      dir_str::binary,
      byte_size(keyset)::32-big,
      keyset::binary
    >>
  end

  defp deserialize(<<@version, rest::binary>>) do
    with {:ok, feed_str, rest} <- read_field(rest),
         {:ok, dir_str, rest} <- read_field(rest),
         {:ok, keyset_str, <<>>} <- read_field(rest),
         {:ok, feed} <- to_existing_atom(feed_str),
         {:ok, direction} <- parse_direction(dir_str),
         :ok <- validate_keyset(keyset_str) do
      {:ok, %{feed: feed, direction: direction, keyset: keyset_str}}
    end
  end

  defp deserialize(_), do: {:error, :invalid_cursor}

  defp read_field(<<len::32-big, rest::binary>>) when byte_size(rest) >= len do
    <<field::binary-size(len), remaining::binary>> = rest
    {:ok, field, remaining}
  end

  defp read_field(_), do: {:error, :invalid_cursor}

  defp to_existing_atom(str) do
    {:ok, String.to_existing_atom(str)}
  rescue
    ArgumentError -> {:error, :invalid_cursor}
  end

  defp parse_direction("next"), do: {:ok, :next}
  defp parse_direction("prev"), do: {:ok, :prev}
  defp parse_direction(_), do: {:error, :invalid_cursor}

  defp validate_keyset(keyset) do
    if String.valid?(keyset) do
      :ok
    else
      {:error, :invalid_cursor}
    end
  end

  # ---------------------------------------------------------------------------
  # HMAC helpers
  # ---------------------------------------------------------------------------

  defp compute_hmac(data) do
    :crypto.mac(:hmac, :sha256, @hmac_key, data)
  end

  defp safe_url_decode64(input) do
    Base.url_decode64(input, padding: false)
  rescue
    _ -> :error
  end

  defp secure_compare(a, b) when is_binary(a) and is_binary(b) do
    if byte_size(a) == byte_size(b) do
      constant_time_compare(a, b)
    else
      false
    end
  end

  defp secure_compare(_, _), do: false

  defp constant_time_compare(<<a, rest_a::binary>>, <<b, rest_b::binary>>) do
    bxor(a, b) == 0 and constant_time_compare(rest_a, rest_b)
  end

  defp constant_time_compare(<<>>, <<>>), do: true
  defp constant_time_compare(_, _), do: false
end
