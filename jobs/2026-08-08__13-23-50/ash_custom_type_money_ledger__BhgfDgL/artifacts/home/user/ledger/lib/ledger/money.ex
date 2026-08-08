defmodule Ledger.Money do
  @moduledoc """
  An exact-integer money value.

  A `Ledger.Money` is a struct with a `:currency` (an atom) and an `:amount`
  (an integer count of *minor units*). All arithmetic is exact integer
  arithmetic - there are no floats, no rounding, and no truncation anywhere
  in this module.
  """

  @enforce_keys [:currency, :amount]
  defstruct [:currency, :amount]

  @type t :: %__MODULE__{currency: atom(), amount: integer()}

  @currency_info %{
    bhd: %{code: "BHD", exponent: 3},
    eur: %{code: "EUR", exponent: 2},
    jpy: %{code: "JPY", exponent: 0},
    usd: %{code: "USD", exponent: 2}
  }

  @currencies [:bhd, :eur, :jpy, :usd]

  @doc "Returns the list of supported currencies, in a stable order."
  @spec currencies() :: [atom()]
  def currencies, do: @currencies

  @doc "Returns true if the given atom is a supported currency."
  @spec supported_currency?(term()) :: boolean()
  def supported_currency?(currency), do: Map.has_key?(@currency_info, currency)

  @doc "Returns the minor-unit exponent for a supported currency."
  @spec exponent(atom()) :: non_neg_integer()
  for {currency, %{exponent: exponent}} <- @currency_info do
    def exponent(unquote(currency)), do: unquote(exponent)
  end

  @doc "Returns the uppercase currency code for a supported currency."
  @spec code(atom()) :: String.t()
  for {currency, %{code: code}} <- @currency_info do
    def code(unquote(currency)), do: unquote(code)
  end

  @doc "Finds the currency atom for a given uppercase currency code, if any."
  @spec currency_for_code(String.t()) :: {:ok, atom()} | :error
  def currency_for_code(code) when is_binary(code) do
    upcased = String.upcase(code)

    Enum.find_value(@currencies, :error, fn currency ->
      if Map.fetch!(@currency_info, currency).code == upcased do
        {:ok, currency}
      end
    end)
  end

  def currency_for_code(_), do: :error

  @doc """
  Builds a new money value.

  Returns `{:ok, money}`, or `{:error, :unknown_currency}` if the currency is
  not supported, or `{:error, :invalid_amount}` if the amount is not an
  integer.
  """
  @spec new(integer(), atom()) ::
          {:ok, t()} | {:error, :unknown_currency} | {:error, :invalid_amount}
  def new(amount, currency) do
    cond do
      not supported_currency?(currency) -> {:error, :unknown_currency}
      not is_integer(amount) -> {:error, :invalid_amount}
      true -> {:ok, %__MODULE__{currency: currency, amount: amount}}
    end
  end

  @doc "Same as `new/2`, but raises `ArgumentError` on failure."
  @spec new!(integer(), atom()) :: t()
  def new!(amount, currency) do
    case new(amount, currency) do
      {:ok, money} ->
        money

      {:error, reason} ->
        raise ArgumentError,
              "invalid money value (amount: #{inspect(amount)}, currency: #{inspect(currency)}): #{inspect(reason)}"
    end
  end

  @doc "Returns a zero-amount money value in the given currency."
  @spec zero(atom()) :: t()
  def zero(currency), do: new!(0, currency)

  @doc """
  Adds two money values of the same currency.

  Returns `{:error, :currency_mismatch}` if the currencies differ.
  """
  @spec add(t(), t()) :: {:ok, t()} | {:error, :currency_mismatch}
  def add(%__MODULE__{currency: currency, amount: left}, %__MODULE__{
        currency: currency,
        amount: right
      }) do
    {:ok, %__MODULE__{currency: currency, amount: left + right}}
  end

  def add(%__MODULE__{}, %__MODULE__{}), do: {:error, :currency_mismatch}

  @doc """
  Subtracts the second money value from the first.

  Returns `{:error, :currency_mismatch}` if the currencies differ.
  """
  @spec subtract(t(), t()) :: {:ok, t()} | {:error, :currency_mismatch}
  def subtract(%__MODULE__{currency: currency, amount: left}, %__MODULE__{
        currency: currency,
        amount: right
      }) do
    {:ok, %__MODULE__{currency: currency, amount: left - right}}
  end

  def subtract(%__MODULE__{}, %__MODULE__{}), do: {:error, :currency_mismatch}

  @doc """
  Multiplies a money value by an integer factor.

  Returns `{:error, :invalid_factor}` if the factor is not an integer.
  """
  @spec multiply(t(), integer()) :: {:ok, t()} | {:error, :invalid_factor}
  def multiply(%__MODULE__{currency: currency, amount: amount}, factor)
      when is_integer(factor) do
    {:ok, %__MODULE__{currency: currency, amount: amount * factor}}
  end

  def multiply(%__MODULE__{}, _factor), do: {:error, :invalid_factor}

  @doc """
  Sums a list of money values, all expected to be in `currency`.

  An empty list sums to zero of that currency. Returns
  `{:error, :currency_mismatch}` if any element uses a different currency.
  """
  @spec sum([t()], atom()) :: {:ok, t()} | {:error, :currency_mismatch}
  def sum(list, currency) when is_list(list) do
    Enum.reduce_while(list, {:ok, zero(currency)}, fn money, {:ok, acc} ->
      case add(acc, money) do
        {:ok, new_acc} -> {:cont, {:ok, new_acc}}
        {:error, reason} -> {:halt, {:error, reason}}
      end
    end)
  end

  @doc """
  Compares two money values of the same currency.

  Returns `:lt`, `:eq` or `:gt`. Raises `ArgumentError` if the currencies
  differ.
  """
  @spec compare(t(), t()) :: :lt | :eq | :gt
  def compare(%__MODULE__{currency: currency, amount: left}, %__MODULE__{
        currency: currency,
        amount: right
      }) do
    cond do
      left < right -> :lt
      left > right -> :gt
      true -> :eq
    end
  end

  def compare(%__MODULE__{}, %__MODULE__{}) do
    raise ArgumentError, "cannot compare money in different currencies"
  end

  @doc "Renders a money value in its canonical string form, e.g. `\"USD 12.50\"`."
  @spec to_string(t()) :: String.t()
  def to_string(%__MODULE__{currency: currency, amount: amount}) do
    code = code(currency)

    case exponent(currency) do
      0 ->
        "#{code} #{amount}"

      exponent ->
        sign = if amount < 0, do: "-", else: ""
        digits = amount |> abs() |> Integer.to_string() |> String.pad_leading(exponent + 1, "0")
        {major, minor} = String.split_at(digits, String.length(digits) - exponent)
        "#{code} #{sign}#{major}.#{minor}"
    end
  end
end
