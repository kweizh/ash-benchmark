defmodule Ledger.Money.Type do
  @moduledoc """
  An `Ash.Type` whose valid instances are `Ledger.Money` structs.

  Accepts, on cast:

    * `nil`
    * a `Ledger.Money` struct
    * a map with `:currency`/`:amount` or `"currency"`/`"amount"` keys
    * the canonical string form, e.g. `"USD 12.50"`

  Stored (and therefore round-tripped through the data layer, and through
  `Jason`) as a plain map: `%{"currency" => "USD", "amount" => 1250}`.

  ### Constraints

    * `:currencies` - the list of currency atoms that are allowed
    * `:min` - an inclusive minimum bound (any accepted input shape)
    * `:max` - an inclusive maximum bound (any accepted input shape)
    * `:multiple_of` - a positive integer the amount must be a multiple of
  """

  use Ash.Type

  alias Ledger.Money

  @integer_re ~r/^-?[0-9]+$/
  @fractional_re ~r/^-?[0-9]+\.[0-9]+$/
  @digits_re ~r/^[0-9]+$/

  @impl true
  def storage_type(_), do: :map

  @impl true
  def constraints do
    [
      currencies: [
        type: {:list, :atom},
        doc: "The list of currencies that are allowed."
      ],
      min: [
        type: :any,
        doc: "The inclusive minimum amount."
      ],
      max: [
        type: :any,
        doc: "The inclusive maximum amount."
      ],
      multiple_of: [
        type: :pos_integer,
        doc: "The amount must be an exact multiple of this many minor units."
      ]
    ]
  end

  @impl true
  def matches_type?(%Money{}, _), do: true
  def matches_type?(_, _), do: false

  # --- casting ---------------------------------------------------------

  @impl true
  def cast_input(nil, _constraints), do: {:ok, nil}
  def cast_input(%Money{} = money, _constraints), do: {:ok, money}

  def cast_input(value, _constraints) when is_binary(value) do
    case parse_money_string(value) do
      {:ok, money} -> {:ok, money}
      {:error, :unknown_currency, raw} -> currency_error(raw)
      {:error, :invalid_format} -> invalid_format_error()
    end
  end

  def cast_input(value, _constraints) when is_map(value) and not is_struct(value) do
    with {:ok, currency_raw} <- fetch_field(value, :currency, "currency"),
         {:ok, amount_raw} <- fetch_field(value, :amount, "amount") do
      case resolve_currency(currency_raw) do
        {:ok, currency} ->
          case resolve_amount(amount_raw) do
            {:ok, amount} -> {:ok, %Money{currency: currency, amount: amount}}
            {:error, :fractional} -> fractional_error()
            {:error, :invalid} -> invalid_format_error()
          end

        :error ->
          currency_error(currency_raw)
      end
    else
      :error -> invalid_format_error()
    end
  end

  def cast_input(_value, _constraints), do: invalid_format_error()

  @impl true
  def cast_stored(nil, _constraints), do: {:ok, nil}

  def cast_stored(%{"currency" => code, "amount" => amount}, _constraints)
      when is_binary(code) and is_integer(amount) do
    case Money.currency_for_code(code) do
      {:ok, currency} -> {:ok, %Money{currency: currency, amount: amount}}
      :error -> invalid_format_error()
    end
  end

  def cast_stored(_value, _constraints), do: invalid_format_error()

  @impl true
  def dump_to_native(nil, _constraints), do: {:ok, nil}

  def dump_to_native(%Money{currency: currency, amount: amount}, _constraints) do
    {:ok, %{"currency" => Money.code(currency), "amount" => amount}}
  end

  def dump_to_native(_value, _constraints), do: :error

  # --- constraints -------------------------------------------------------

  @impl true
  def apply_constraints(nil, _constraints), do: {:ok, nil}

  def apply_constraints(%Money{} = money, constraints) do
    with :ok <- check_currencies(money, constraints[:currencies]),
         :ok <- check_multiple_of(money, constraints[:multiple_of]),
         :ok <- check_min(money, constraints[:min]),
         :ok <- check_max(money, constraints[:max]) do
      {:ok, money}
    end
  end

  defp check_currencies(_money, nil), do: :ok

  defp check_currencies(money, currencies) do
    if money.currency in currencies do
      :ok
    else
      {:error, [message: "currency is not allowed", reason: :currency_not_allowed, currency: money.currency]}
    end
  end

  defp check_multiple_of(_money, nil), do: :ok

  defp check_multiple_of(money, multiple_of) do
    if rem(money.amount, multiple_of) == 0 do
      :ok
    else
      {:error,
       [
         message: "must be a multiple of %{multiple_of} minor units",
         reason: :not_multiple_of,
         multiple_of: multiple_of
       ]}
    end
  end

  defp check_min(_money, nil), do: :ok

  defp check_min(money, raw_bound) do
    case resolve_bound(raw_bound) do
      {:ok, bound} ->
        cond do
          bound.currency != money.currency ->
            currency_mismatch_error()

          money.amount < bound.amount ->
            {:error,
             [
               message: "must be greater than or equal to %{min}",
               reason: :below_min,
               min: Money.to_string(bound)
             ]}

          true ->
            :ok
        end

      :error ->
        :ok
    end
  end

  defp check_max(_money, nil), do: :ok

  defp check_max(money, raw_bound) do
    case resolve_bound(raw_bound) do
      {:ok, bound} ->
        cond do
          bound.currency != money.currency ->
            currency_mismatch_error()

          money.amount > bound.amount ->
            {:error,
             [
               message: "must be less than or equal to %{max}",
               reason: :above_max,
               max: Money.to_string(bound)
             ]}

          true ->
            :ok
        end

      :error ->
        :ok
    end
  end

  defp currency_mismatch_error do
    {:error, [message: "cannot compare money in different currencies", reason: :currency_mismatch]}
  end

  defp resolve_bound(%Money{} = money), do: {:ok, money}

  defp resolve_bound(raw) do
    case cast_input(raw, []) do
      {:ok, %Money{} = money} -> {:ok, money}
      _ -> :error
    end
  end

  # --- helpers -----------------------------------------------------------

  defp fetch_field(map, atom_key, string_key) do
    cond do
      Map.has_key?(map, atom_key) -> {:ok, Map.get(map, atom_key)}
      Map.has_key?(map, string_key) -> {:ok, Map.get(map, string_key)}
      true -> :error
    end
  end

  defp resolve_currency(currency) when is_atom(currency) and not is_nil(currency) do
    if Money.supported_currency?(currency), do: {:ok, currency}, else: :error
  end

  defp resolve_currency(currency) when is_binary(currency) do
    Money.currency_for_code(currency)
  end

  defp resolve_currency(_currency), do: :error

  defp resolve_amount(amount) when is_integer(amount), do: {:ok, amount}
  defp resolve_amount(amount) when is_float(amount), do: {:error, :fractional}

  defp resolve_amount(amount) when is_binary(amount) do
    cond do
      Regex.match?(@integer_re, amount) -> {:ok, String.to_integer(amount)}
      Regex.match?(@fractional_re, amount) -> {:error, :fractional}
      true -> {:error, :invalid}
    end
  end

  defp resolve_amount(_amount), do: {:error, :invalid}

  defp parse_money_string(string) do
    case String.split(string, " ", parts: 2) do
      [code_part, amount_part] ->
        case resolve_currency(code_part) do
          {:ok, currency} ->
            case parse_canonical_amount(amount_part, Money.exponent(currency)) do
              {:ok, amount} -> {:ok, %Money{currency: currency, amount: amount}}
              :error -> {:error, :invalid_format}
            end

          :error ->
            {:error, :unknown_currency, code_part}
        end

      _ ->
        {:error, :invalid_format}
    end
  end

  defp parse_canonical_amount(string, exponent) do
    {sign, unsigned} =
      case string do
        "-" <> rest -> {-1, rest}
        _ -> {1, string}
      end

    case String.split(unsigned, ".", parts: 2) do
      [major] ->
        cond do
          exponent != 0 -> :error
          not digits?(major) -> :error
          true -> {:ok, sign * String.to_integer(major)}
        end

      [major, minor] ->
        cond do
          exponent == 0 -> :error
          not digits?(major) -> :error
          not digits?(minor) -> :error
          String.length(minor) != exponent -> :error
          true -> {:ok, sign * String.to_integer(major <> minor)}
        end
    end
  end

  defp digits?(value), do: value != "" and Regex.match?(@digits_re, value)

  defp currency_error(raw) do
    {:error, [message: "unknown currency", reason: :unknown_currency, currency: raw]}
  end

  defp fractional_error do
    {:error, [message: "amount must be a whole number of minor units", reason: :fractional_minor_units]}
  end

  defp invalid_format_error do
    {:error, [message: "invalid money format", reason: :invalid_format]}
  end
end
