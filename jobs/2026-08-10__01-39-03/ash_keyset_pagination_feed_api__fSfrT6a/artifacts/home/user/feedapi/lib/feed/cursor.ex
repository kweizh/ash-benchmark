defmodule Feed.Cursor do
  @moduledoc """
  An opaque, tamper-evident cursor codec used by `Feed.Api` to drive
  keyset-based pagination.

  A cursor carries three pieces of information:

    * `:feed` - the name of the feed action the cursor was issued for
    * `:direction` - whether the cursor should be applied as a `:next` or
      `:prev` continuation
    * `:keyset` - the opaque Ash keyset value for the anchor record

  The wire format is a URL-safe Base64 string (no padding) wrapping the
  term-encoded payload, an explicit padding-length byte, and an HMAC. The
  payload is zero-padded so that the raw byte length is always a multiple
  of three - this guarantees the Base64 rendering never contains "don't
  care" bits, so every character in the string is significant. Combined
  with the HMAC, this means any corruption - including a payload that was
  hand-assembled without going through `encode/1` - is reliably rejected by
  `decode/1`.
  """

  @secret "feed.cursor.v1:9f1c2b7a4d6e8f0a"
  @mac_size 16

  @type direction :: :next | :prev
  @type payload :: %{feed: atom(), direction: direction(), keyset: String.t()}

  @doc """
  Encodes a cursor payload into an opaque, URL-safe string.

  Encoding the same payload twice always produces the same string.
  """
  @spec encode(payload()) :: String.t()
  def encode(%{feed: feed, direction: direction, keyset: keyset})
      when is_atom(feed) and direction in [:next, :prev] and is_binary(keyset) do
    bin = :erlang.term_to_binary({feed, direction, keyset})
    pad_len = pad_len_for(byte_size(bin))
    padded_bin = bin <> :binary.copy(<<0>>, pad_len)
    signed_part = padded_bin <> <<pad_len>>
    mac = mac_for(signed_part)

    Base.url_encode64(signed_part <> mac, padding: false)
  end

  @doc """
  Decodes a cursor string produced by `encode/1`.

  Returns `{:ok, payload}` on success, and `{:error, :invalid_cursor}` for
  any binary that is not a cursor produced by `encode/1` - including
  truncated, corrupted, or hand-assembled inputs. Never raises.
  """
  @spec decode(binary()) :: {:ok, payload()} | {:error, :invalid_cursor}
  def decode(cursor) when is_binary(cursor) do
    case Base.url_decode64(cursor, padding: false) do
      {:ok, combined} -> decode_combined(combined)
      :error -> {:error, :invalid_cursor}
    end
  end

  def decode(_cursor), do: {:error, :invalid_cursor}

  defp decode_combined(combined) when byte_size(combined) > @mac_size + 1 do
    signed_size = byte_size(combined) - @mac_size
    <<signed_part::binary-size(signed_size), mac::binary-size(@mac_size)>> = combined

    if mac == mac_for(signed_part) do
      unpad_and_decode(signed_part)
    else
      {:error, :invalid_cursor}
    end
  end

  defp decode_combined(_combined), do: {:error, :invalid_cursor}

  defp unpad_and_decode(signed_part) do
    padded_size = byte_size(signed_part) - 1
    <<padded_bin::binary-size(padded_size), pad_len>> = signed_part

    with true <- pad_len in 0..2,
         real_size when real_size >= 0 <- byte_size(padded_bin) - pad_len,
         <<bin::binary-size(real_size), pad::binary-size(pad_len)>> <- padded_bin,
         true <- pad == :binary.copy(<<0>>, pad_len) do
      decode_term(bin)
    else
      _ -> {:error, :invalid_cursor}
    end
  end

  defp decode_term(bin) do
    case :erlang.binary_to_term(bin, [:safe]) do
      {feed, direction, keyset}
      when is_atom(feed) and direction in [:next, :prev] and is_binary(keyset) ->
        {:ok, %{feed: feed, direction: direction, keyset: keyset}}

      _ ->
        {:error, :invalid_cursor}
    end
  rescue
    _ -> {:error, :invalid_cursor}
  end

  # Picks a padding length (0, 1 or 2 zero bytes) so that
  # `bin_size + pad_len + 1 (pad_len byte) + mac_size` is a multiple of 3,
  # ensuring the final Base64 string has no partial trailing group.
  defp pad_len_for(bin_size) do
    base = bin_size + 1 + @mac_size
    rem(3 - rem(base, 3), 3)
  end

  defp mac_for(bin) do
    :hmac
    |> :crypto.mac(:sha256, @secret, bin)
    |> binary_part(0, @mac_size)
  end
end
