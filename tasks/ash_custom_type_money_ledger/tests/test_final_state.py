import base64
import os
import subprocess

import pytest

PROJECT_DIR = "/home/user/ledger"
SUITE_PATH = "/tmp/harbor_money_suite.exs"
MARKER = "@@HARBOR@@"

SUITE_EXS = r"""
defmodule HarborFormatter do
  @moduledoc false
  use GenServer

  def init(_opts), do: {:ok, %{}}

  def handle_cast({:test_finished, %ExUnit.Test{} = test}, state) do
    {status, detail} =
      case test.state do
        nil ->
          {"pass", ""}

        {:excluded, _} ->
          {"skip", ""}

        {:skipped, _} ->
          {"skip", ""}

        {:invalid, _} ->
          {"fail", "test module failed to set up"}

        {:failed, failures} ->
          formatted =
            ExUnit.Formatter.format_test_failure(test, failures, 1, 120, fn _kind, msg -> msg end)

          {"fail", formatted}
      end

    IO.puts("@@HARBOR@@" <> Atom.to_string(test.name) <> "@@" <> status <> "@@" <> Base.encode64(detail))
    {:noreply, state}
  end

  def handle_cast(_message, state), do: {:noreply, state}
end

ExUnit.start(
  autorun: false,
  formatters: [HarborFormatter],
  seed: 0,
  colors: [enabled: false],
  timeout: 120_000
)

defmodule H do
  @moduledoc false

  def money_mod, do: Module.concat(["Ledger", "Money"])
  def type_mod, do: Module.concat(["Ledger", "Money", "Type"])
  def usd_mod, do: Module.concat(["Ledger", "Money", "Usd"])
  def billing, do: Module.concat(["Ledger", "Billing"])
  def invoice, do: Module.concat(["Ledger", "Billing", "Invoice"])
  def payment, do: Module.concat(["Ledger", "Billing", "Payment"])

  def call(mod, fun, args), do: apply(mod, fun, args)
  def money(fun, args), do: apply(money_mod(), fun, args)
  def bill(fun, args), do: apply(billing(), fun, args)

  def m(amount, currency), do: struct(money_mod(), %{currency: currency, amount: amount})

  def parts(nil), do: nil
  def parts(value) when is_map(value), do: {Map.get(value, :currency), Map.get(value, :amount)}

  def cast(value, constraints \\ []), do: Ash.Type.cast_input(type_mod(), value, constraints)

  def constrain(value, constraints),
    do: Ash.Type.apply_constraints(type_mod(), value, constraints)

  def failure({:error, keyword}) when is_list(keyword), do: keyword
  def failure(other), do: flunk_value(other)

  def array_failure({:error, [entry | _]}) when is_list(entry), do: entry
  def array_failure({:error, keyword}) when is_list(keyword), do: keyword
  def array_failure(other), do: flunk_value(other)

  defp flunk_value(other) do
    raise "expected an {:error, keyword} tuple, got: #{inspect(other)}"
  end

  def errors({:error, %{errors: errors}}), do: errors
  def errors(other), do: raise("expected an error result, got: #{inspect(other)}")

  def error_on(result, field) do
    case Enum.find(errors(result), fn error -> Map.get(error, :field) == field end) do
      nil -> raise "no error on field #{inspect(field)} in #{inspect(errors(result))}"
      error -> error
    end
  end

  def vars(error), do: Map.get(error, :vars) || []

  def issue(params), do: bill(:issue_invoice, [params])
  def issue!(params), do: bill(:issue_invoice!, [params])
end

defmodule HarborMoneyTest do
  use ExUnit.Case, async: false
  require Ash.Query

  test "T01 supported currencies and their minor unit exponents" do
    assert H.money(:currencies, []) == [:bhd, :eur, :jpy, :usd]
    assert H.money(:exponent, [:usd]) == 2
    assert H.money(:exponent, [:eur]) == 2
    assert H.money(:exponent, [:jpy]) == 0
    assert H.money(:exponent, [:bhd]) == 3
  end

  test "T02 constructing money values" do
    assert {:ok, value} = H.money(:new, [1250, :usd])
    assert H.parts(value) == {:usd, 1250}
    assert H.money(:new, [1250, :gbp]) == {:error, :unknown_currency}
    assert H.money(:new, [12.5, :usd]) == {:error, :invalid_amount}
    assert H.parts(H.money(:new!, [1250, :usd])) == {:usd, 1250}
    assert_raise ArgumentError, fn -> H.money(:new!, [1250, :gbp]) end
    assert H.parts(H.money(:zero, [:jpy])) == {:jpy, 0}
    assert H.parts(H.money(:zero, [:bhd])) == {:bhd, 0}
  end

  test "T03 canonical string rendering" do
    assert H.money(:to_string, [H.m(1250, :usd)]) == "USD 12.50"
    assert H.money(:to_string, [H.m(-5, :usd)]) == "USD -0.05"
    assert H.money(:to_string, [H.m(0, :usd)]) == "USD 0.00"
    assert H.money(:to_string, [H.m(500, :jpy)]) == "JPY 500"
    assert H.money(:to_string, [H.m(-7, :jpy)]) == "JPY -7"
    assert H.money(:to_string, [H.m(1234, :bhd)]) == "BHD 1.234"
    assert H.money(:to_string, [H.m(-1, :bhd)]) == "BHD -0.001"
    assert H.money(:to_string, [H.m(105, :eur)]) == "EUR 1.05"
  end

  test "T04 addition and subtraction are exact and currency safe" do
    assert {:ok, sum} = H.money(:add, [H.m(1250, :usd), H.m(-300, :usd)])
    assert H.parts(sum) == {:usd, 950}
    assert {:ok, difference} = H.money(:subtract, [H.m(1250, :usd), H.m(-300, :usd)])
    assert H.parts(difference) == {:usd, 1550}
    assert H.money(:add, [H.m(1, :usd), H.m(1, :eur)]) == {:error, :currency_mismatch}
    assert H.money(:subtract, [H.m(1, :usd), H.m(1, :eur)]) == {:error, :currency_mismatch}
  end

  test "T05 multiplication by integers" do
    assert {:ok, quadrupled} = H.money(:multiply, [H.m(125, :usd), 4])
    assert H.parts(quadrupled) == {:usd, 500}
    assert {:ok, negated} = H.money(:multiply, [H.m(125, :usd), -3])
    assert H.parts(negated) == {:usd, -375}
    assert {:ok, zeroed} = H.money(:multiply, [H.m(125, :usd), 0])
    assert H.parts(zeroed) == {:usd, 0}
    assert H.money(:multiply, [H.m(125, :usd), 1.5]) == {:error, :invalid_factor}
  end

  test "T06 summing lists of money" do
    assert {:ok, total} =
             H.money(:sum, [[H.m(100, :usd), H.m(-25, :usd), H.m(5, :usd)], :usd])

    assert H.parts(total) == {:usd, 80}
    assert {:ok, empty} = H.money(:sum, [[], :jpy])
    assert H.parts(empty) == {:jpy, 0}
    assert H.money(:sum, [[H.m(1, :usd), H.m(1, :eur)], :usd]) == {:error, :currency_mismatch}
  end

  test "T07 comparison semantics" do
    assert H.money(:compare, [H.m(1, :usd), H.m(2, :usd)]) == :lt
    assert H.money(:compare, [H.m(2, :usd), H.m(2, :usd)]) == :eq
    assert H.money(:compare, [H.m(3, :usd), H.m(2, :usd)]) == :gt
    assert H.money(:compare, [H.m(-3, :usd), H.m(-2, :usd)]) == :lt
    assert_raise ArgumentError, fn -> H.money(:compare, [H.m(1, :usd), H.m(1, :eur)]) end
  end

  test "T08 every accepted input shape produces the same value" do
    inputs = [
      H.m(1250, :usd),
      %{currency: :usd, amount: 1250},
      %{"currency" => "USD", "amount" => "1250"},
      %{currency: "usd", amount: 1250},
      %{"currency" => :usd, "amount" => 1250},
      "USD 12.50"
    ]

    values =
      Enum.map(inputs, fn input ->
        assert {:ok, value} = H.cast(input), "failed to cast #{inspect(input)}"
        assert H.parts(value) == {:usd, 1250}, "wrong value for #{inspect(input)}"
        value
      end)

    for left <- values, right <- values do
      assert Ash.Type.equal?(H.type_mod(), left, right)
    end

    assert H.cast(nil) == {:ok, nil}
  end

  test "T09 canonical strings round trip for every currency and sign" do
    assert {:ok, jpy} = H.cast("JPY 500")
    assert H.parts(jpy) == {:jpy, 500}
    assert {:ok, jpy_negative} = H.cast("JPY -7")
    assert H.parts(jpy_negative) == {:jpy, -7}
    assert {:ok, bhd} = H.cast("BHD 1.234")
    assert H.parts(bhd) == {:bhd, 1234}
    assert {:ok, bhd_negative} = H.cast("BHD -0.001")
    assert H.parts(bhd_negative) == {:bhd, -1}
    assert {:ok, usd_negative} = H.cast("USD -0.05")
    assert H.parts(usd_negative) == {:usd, -5}
    assert {:ok, zero} = H.cast("USD 0.00")
    assert H.parts(zero) == {:usd, 0}

    for value <- [jpy, jpy_negative, bhd, bhd_negative, usd_negative, zero] do
      assert {:ok, again} = H.cast(H.money(:to_string, [value]))
      assert H.parts(again) == H.parts(value)
    end
  end

  test "T10 unsupported currencies are reported before anything else" do
    failure = H.failure(H.cast(%{"currency" => "XBT", "amount" => 5}))
    assert Keyword.get(failure, :message) == "unknown currency"
    assert Keyword.get(failure, :reason) == :unknown_currency
    assert Keyword.get(failure, :currency) == "XBT"

    atom_failure = H.failure(H.cast(%{currency: :gbp, amount: 5}))
    assert Keyword.get(atom_failure, :reason) == :unknown_currency
    assert Keyword.get(atom_failure, :currency) == :gbp

    string_failure = H.failure(H.cast("XBT 1.00"))
    assert Keyword.get(string_failure, :reason) == :unknown_currency
    assert Keyword.get(string_failure, :currency) == "XBT"

    both_bad = H.failure(H.cast(%{currency: :gbp, amount: 12.5}))
    assert Keyword.get(both_bad, :reason) == :unknown_currency
  end

  test "T11 fractional minor units are rejected" do
    for input <- [%{currency: :usd, amount: 12.5}, %{"currency" => "USD", "amount" => "12.5"}] do
      failure = H.failure(H.cast(input))
      assert Keyword.get(failure, :message) == "amount must be a whole number of minor units"
      assert Keyword.get(failure, :reason) == :fractional_minor_units
    end
  end

  test "T12 unusable input shapes are rejected" do
    inputs = [
      [1, 2],
      %{currency: :usd},
      %{amount: 100},
      "USD12.50",
      "USD 12.5",
      "JPY 5.0",
      "USD abc",
      :usd,
      1250
    ]

    for input <- inputs do
      failure = H.failure(H.cast(input))

      assert Keyword.get(failure, :message) == "invalid money format",
             "wrong message for #{inspect(input)}: #{inspect(failure)}"

      assert Keyword.get(failure, :reason) == :invalid_format,
             "wrong reason for #{inspect(input)}: #{inspect(failure)}"
    end
  end

  test "T13 different currencies and amounts are never equal" do
    refute Ash.Type.equal?(H.type_mod(), H.m(100, :usd), H.m(100, :eur))
    refute Ash.Type.equal?(H.type_mod(), H.m(100, :usd), H.m(1000, :usd))
    assert Ash.Type.equal?(H.type_mod(), H.m(100, :usd), H.m(100, :usd))
  end

  test "T14 the storage type is a map" do
    assert Ash.Type.storage_type(H.type_mod(), []) == :map
  end

  test "T15 dumping and loading is lossless, including through JSON" do
    for value <- [H.m(1250, :usd), H.m(-7, :jpy), H.m(1234, :bhd), H.m(0, :eur)] do
      assert {:ok, dumped} = Ash.Type.dump_to_native(H.type_mod(), value, [])
      assert is_map(dumped), "expected a map storage form, got #{inspect(dumped)}"
      assert {:ok, loaded} = Ash.Type.cast_stored(H.type_mod(), dumped, [])
      assert H.parts(loaded) == H.parts(value)

      round_tripped = Jason.decode!(Jason.encode!(dumped))
      assert {:ok, from_json} = Ash.Type.cast_stored(H.type_mod(), round_tripped, [])
      assert H.parts(from_json) == H.parts(value)
    end
  end

  test "T16 arrays and nil survive the storage round trip" do
    values = [H.m(1250, :usd), H.m(-7, :jpy), H.m(1234, :bhd)]

    assert {:ok, dumped} =
             Ash.Type.dump_to_native({:array, H.type_mod()}, values, items: [])

    round_tripped = Jason.decode!(Jason.encode!(dumped))

    assert {:ok, loaded} =
             Ash.Type.cast_stored({:array, H.type_mod()}, round_tripped, items: [])

    assert Enum.map(loaded, &H.parts/1) == Enum.map(values, &H.parts/1)

    assert Ash.Type.dump_to_native(H.type_mod(), nil, []) == {:ok, nil}
    assert Ash.Type.cast_stored(H.type_mod(), nil, []) == {:ok, nil}
  end

  test "T17 loading a value the type never wrote is rejected" do
    for stored <- [1250, "nonsense", [1, 2]] do
      failure = H.failure(Ash.Type.cast_stored(H.type_mod(), stored, []))
      assert Keyword.get(failure, :reason) == :invalid_format
      assert Keyword.get(failure, :message) == "invalid money format"
    end
  end

  test "T18 the currencies constraint" do
    assert {:ok, allowed} = H.constrain(H.m(100, :usd), currencies: [:usd, :eur])
    assert H.parts(allowed) == {:usd, 100}

    failure = H.failure(H.constrain(H.m(100, :jpy), currencies: [:usd, :eur]))
    assert Keyword.get(failure, :message) == "currency is not allowed"
    assert Keyword.get(failure, :reason) == :currency_not_allowed
    assert Keyword.get(failure, :currency) == :jpy
  end

  test "T19 the multiple_of constraint" do
    for amount <- [100, -15, 0] do
      assert {:ok, _} = H.constrain(H.m(amount, :usd), multiple_of: 5)
    end

    failure = H.failure(H.constrain(H.m(103, :usd), multiple_of: 5))
    assert Keyword.get(failure, :message) == "must be a multiple of %{multiple_of} minor units"
    assert Keyword.get(failure, :reason) == :not_multiple_of
    assert Keyword.get(failure, :multiple_of) == 5
  end

  test "T20 the min and max constraints are inclusive" do
    assert {:ok, _} = H.constrain(H.m(0, :usd), min: "USD 0.00")
    below = H.failure(H.constrain(H.m(-1, :usd), min: "USD 0.00"))
    assert Keyword.get(below, :message) == "must be greater than or equal to %{min}"
    assert Keyword.get(below, :reason) == :below_min
    assert Keyword.get(below, :min) == "USD 0.00"

    assert {:ok, _} = H.constrain(H.m(50, :usd), max: %{currency: :usd, amount: 50})
    above = H.failure(H.constrain(H.m(51, :usd), max: %{currency: :usd, amount: 50}))
    assert Keyword.get(above, :message) == "must be less than or equal to %{max}"
    assert Keyword.get(above, :reason) == :above_max
    assert Keyword.get(above, :max) == "USD 0.50"
  end

  test "T21 bounds in another currency are not comparable" do
    failure = H.failure(H.constrain(H.m(100, :eur), min: "USD 0.00"))
    assert Keyword.get(failure, :message) == "cannot compare money in different currencies"
    assert Keyword.get(failure, :reason) == :currency_mismatch

    max_failure = H.failure(H.constrain(H.m(100, :jpy), max: "USD 1.00"))
    assert Keyword.get(max_failure, :reason) == :currency_mismatch
  end

  test "T22 constraints are checked in the documented order" do
    constraints = [currencies: [:usd], multiple_of: 5, min: "USD 1.00"]

    currency_first = H.failure(H.constrain(H.m(103, :jpy), constraints))
    assert Keyword.get(currency_first, :reason) == :currency_not_allowed

    multiple_before_min = H.failure(H.constrain(H.m(103, :usd), constraints))
    assert Keyword.get(multiple_before_min, :reason) == :not_multiple_of

    min_last = H.failure(H.constrain(H.m(50, :usd), constraints))
    assert Keyword.get(min_last, :reason) == :below_min
  end

  test "T23 array casting reports the failing element index" do
    assert {:ok, casted} =
             Ash.Type.cast_input(
               {:array, H.type_mod()},
               [%{currency: :usd, amount: 100}, "USD 1.00"],
               items: []
             )

    assert Enum.map(casted, &H.parts/1) == [{:usd, 100}, {:usd, 100}]

    entry =
      H.array_failure(
        Ash.Type.cast_input(
          {:array, H.type_mod()},
          ["USD 1.00", "nope", "USD 2.00"],
          items: []
        )
      )

    assert Keyword.get(entry, :index) == 1
    assert Keyword.get(entry, :reason) == :invalid_format
  end

  test "T24 array constraints report the failing element index" do
    entry =
      H.array_failure(
        Ash.Type.apply_constraints(
          {:array, H.type_mod()},
          [H.m(100, :usd), H.m(103, :usd)],
          items: [multiple_of: 5]
        )
      )

    assert Keyword.get(entry, :index) == 1
    assert Keyword.get(entry, :reason) == :not_multiple_of
    assert Keyword.get(entry, :multiple_of) == 5
  end

  test "T25 the narrowed type is a new type over the money type" do
    assert Ash.Type.NewType.new_type?(H.usd_mod())
    assert Ash.Type.NewType.subtype_of(H.usd_mod()) == H.type_mod()
  end

  test "T26 the narrowed type bakes in its constraints" do
    eur = H.error_on(H.issue(%{reference: "N-1", subtotal: "USD 1.00", credit_limit: "EUR 1.00"}), :credit_limit)
    assert Keyword.get(H.vars(eur), :reason) == :currency_not_allowed

    above =
      H.error_on(
        H.issue(%{reference: "N-2", subtotal: "USD 1.00", credit_limit: "USD 10000.01"}),
        :credit_limit
      )

    assert Keyword.get(H.vars(above), :reason) == :above_max
    assert Keyword.get(H.vars(above), :max) == "USD 10000.00"

    below =
      H.error_on(
        H.issue(%{reference: "N-3", subtotal: "USD 1.00", credit_limit: "USD -0.01"}),
        :credit_limit
      )

    assert Keyword.get(H.vars(below), :reason) == :below_min

    assert {:ok, invoice} =
             H.issue(%{reference: "N-4", subtotal: "USD 1.00", credit_limit: "USD 100.00"})

    assert {:ok, reloaded} = H.bill(:get_invoice, [invoice.id])
    assert H.parts(reloaded.credit_limit) == {:usd, 10000}
  end

  test "T27 money survives the data layer round trip" do
    assert {:ok, invoice} =
             H.issue(%{
               reference: "INV-1",
               subtotal: %{"currency" => "USD", "amount" => 1250},
               adjustments: ["USD 0.05", %{currency: :usd, amount: -10}],
               credit_limit: "USD 100.00"
             })

    assert {:ok, reloaded} = H.bill(:get_invoice, [invoice.id])
    assert reloaded.reference == "INV-1"
    assert H.parts(reloaded.subtotal) == {:usd, 1250}
    assert Enum.map(reloaded.adjustments, &H.parts/1) == [{:usd, 5}, {:usd, -10}]
    assert H.parts(reloaded.credit_limit) == {:usd, 10000}

    assert {:ok, listed} = H.bill(:list_invoices, [])
    assert Enum.map(listed, & &1.reference) == ["INV-1"]

    assert {:ok, defaulted} = H.issue(%{reference: "INV-2", subtotal: "JPY 500"})
    assert defaulted.adjustments == []
    assert defaulted.credit_limit == nil
  end

  test "T28 attribute currency constraints reject disallowed currencies" do
    error = H.error_on(H.issue(%{reference: "BAD", subtotal: "BHD 1.000"}), :subtotal)
    assert error.__struct__ == Ash.Error.Changes.InvalidAttribute
    assert error.message == "currency is not allowed"
    assert Keyword.get(H.vars(error), :reason) == :currency_not_allowed
    assert Keyword.get(H.vars(error), :currency) == :bhd
  end

  test "T29 array element constraints report the index on the resource" do
    error =
      H.error_on(
        H.issue(%{
          reference: "BAD",
          subtotal: "USD 1.00",
          adjustments: ["USD 0.05", "USD 0.03", "USD 0.10"]
        }),
        :adjustments
      )

    assert error.__struct__ == Ash.Error.Changes.InvalidAttribute
    assert Keyword.get(H.vars(error), :index) == 1
    assert Keyword.get(H.vars(error), :reason) == :not_multiple_of
  end

  test "T30 adjustments must use the currency of the subtotal" do
    error =
      H.error_on(
        H.issue(%{reference: "MIX", subtotal: "USD 1.00", adjustments: ["EUR 0.05"]}),
        :adjustments
      )

    assert error.__struct__ == Ash.Error.Changes.InvalidAttribute
    assert error.message == "must all use the currency of the subtotal"
  end

  test "T31 applying adjustments appends them in order" do
    assert {:ok, invoice} = H.issue(%{reference: "ADJ", subtotal: "USD 12.50"})
    assert {:ok, once} = H.bill(:apply_adjustment, [invoice, "USD 0.25"])
    assert Enum.map(once.adjustments, &H.parts/1) == [{:usd, 25}]

    assert {:ok, twice} = H.bill(:apply_adjustment, [once, %{currency: :usd, amount: -5}])
    assert Enum.map(twice.adjustments, &H.parts/1) == [{:usd, 25}, {:usd, -5}]

    assert {:ok, reloaded} = H.bill(:get_invoice, [invoice.id])
    assert Enum.map(reloaded.adjustments, &H.parts/1) == [{:usd, 25}, {:usd, -5}]
  end

  test "T32 an adjustment in another currency is rejected without touching the record" do
    assert {:ok, invoice} = H.issue(%{reference: "ADJ2", subtotal: "USD 12.50"})
    assert {:ok, invoice} = H.bill(:apply_adjustment, [invoice, "USD 0.25"])

    result = H.bill(:apply_adjustment, [invoice, "EUR 0.25"])
    error = H.error_on(result, :adjustment)
    assert error.__struct__ == Ash.Error.Changes.InvalidArgument
    assert error.message == "must use the currency of the subtotal"

    assert {:ok, reloaded} = H.bill(:get_invoice, [invoice.id])
    assert Enum.map(reloaded.adjustments, &H.parts/1) == [{:usd, 25}]
  end

  test "T33 an adjustment breaking the element constraint leaves the record untouched" do
    assert {:ok, invoice} = H.issue(%{reference: "ADJ3", subtotal: "USD 12.50"})
    assert {:ok, invoice} = H.bill(:apply_adjustment, [invoice, "USD 0.25"])

    assert {:error, _} = H.bill(:apply_adjustment, [invoice, "USD 0.03"])

    assert {:ok, reloaded} = H.bill(:get_invoice, [invoice.id])
    assert Enum.map(reloaded.adjustments, &H.parts/1) == [{:usd, 25}]
  end

  test "T34 the total calculation folds the adjustments in" do
    assert {:ok, invoice} =
             H.issue(%{
               reference: "CALC",
               subtotal: "USD 12.50",
               adjustments: ["USD 0.05", "USD -0.10"]
             })

    assert {:ok, loaded} = Ash.load(invoice, [:total, :balance, :paid_minor])
    assert H.parts(loaded.total) == {:usd, 1245}
    assert loaded.paid_minor == 0
    assert H.parts(loaded.balance) == {:usd, 1245}

    assert {:ok, plain} = H.issue(%{reference: "CALC2", subtotal: "JPY 500"})
    assert {:ok, plain_loaded} = Ash.load(plain, [:total])
    assert H.parts(plain_loaded.total) == {:jpy, 500}
  end

  test "T35 payments feed the aggregate and the balance" do
    assert {:ok, invoice} = H.issue(%{reference: "PAY", subtotal: "USD 12.50"})

    assert {:ok, payment} = H.bill(:record_payment, [%{amount: "USD 5.00", invoice_id: invoice.id}])
    assert H.parts(payment.amount) == {:usd, 500}
    assert payment.amount_minor == 500
    assert payment.amount_currency == :usd

    assert {:ok, _} = H.bill(:record_payment, [%{amount: "USD 2.50", invoice_id: invoice.id}])

    assert {:ok, reloaded} = H.bill(:get_invoice, [invoice.id])
    assert {:ok, loaded} = Ash.load(reloaded, [:total, :paid_minor, :balance])
    assert loaded.paid_minor == 750
    assert H.parts(loaded.total) == {:usd, 1250}
    assert H.parts(loaded.balance) == {:usd, 500}
  end

  test "T36 derived payment columns cannot be supplied and currencies are enforced" do
    assert {:ok, invoice} = H.issue(%{reference: "PAY2", subtotal: "USD 12.50"})

    smuggled =
      H.bill(:record_payment, [
        %{amount: "USD 1.00", invoice_id: invoice.id, amount_minor: 999_999}
      ])

    assert {:error, %{errors: errors}} = smuggled

    assert Enum.any?(errors, fn error ->
             error.__struct__ == Ash.Error.Invalid.NoSuchInput
           end),
           "expected a NoSuchInput error, got #{inspect(errors)}"

    rejected = H.bill(:record_payment, [%{amount: "BHD 1.000", invoice_id: invoice.id}])
    error = H.error_on(rejected, :amount)
    assert Keyword.get(H.vars(error), :reason) == :currency_not_allowed
  end

  test "T37 the derived minor unit column is an ordinary queryable integer" do
    assert {:ok, invoice} = H.issue(%{reference: "PAY3", subtotal: "USD 100.00"})

    for amount <- ["USD 1.00", "USD 5.00", "USD 20.00"] do
      assert {:ok, _} = H.bill(:record_payment, [%{amount: amount, invoice_id: invoice.id}])
    end

    assert {:ok, big} =
             H.payment()
             |> Ash.Query.filter(amount_minor > 400)
             |> Ash.Query.sort(amount_minor: :asc)
             |> Ash.read()

    assert Enum.map(big, & &1.amount_minor) == [500, 2000]
  end

  test "T38 the generic action returns money" do
    assert {:ok, priced} = H.bill(:price_for, ["USD 1.25", 4])
    assert H.parts(priced) == {:usd, 500}

    assert {:ok, jpy} = H.bill(:price_for, [%{currency: :jpy, amount: 7}, 3])
    assert H.parts(jpy) == {:jpy, 21}

    result = H.bill(:price_for, ["XBT 1.25", 4])
    error = H.error_on(result, :unit_price)
    assert Keyword.get(H.vars(error), :reason) == :unknown_currency
  end

  test "T39 sorting by money orders by amount, not lexicographically" do
    for {reference, subtotal} <- [
          {"S-A", "USD 0.05"},
          {"S-B", "USD 9.00"},
          {"S-C", "USD 100.00"},
          {"S-D", "USD 12.50"}
        ] do
      assert {:ok, _} = H.issue(%{reference: reference, subtotal: subtotal})
    end

    assert {:ok, ascending} =
             H.invoice()
             |> Ash.Query.sort(subtotal: :asc)
             |> Ash.read()

    assert Enum.map(ascending, & &1.subtotal.amount) == [5, 900, 1250, 10000]

    assert {:ok, descending} =
             H.invoice()
             |> Ash.Query.sort(subtotal: :desc)
             |> Ash.read()

    assert Enum.map(descending, & &1.subtotal.amount) == [10000, 1250, 900, 5]
  end

  test "T40 equality filters match currency and amount together" do
    assert {:ok, _} = H.issue(%{reference: "F-USD", subtotal: "USD 9.00"})
    assert {:ok, _} = H.issue(%{reference: "F-EUR", subtotal: "EUR 9.00"})
    assert {:ok, _} = H.issue(%{reference: "F-OTHER", subtotal: "USD 100.00"})

    target = H.m(900, :usd)

    assert {:ok, matched} =
             H.invoice()
             |> Ash.Query.filter(subtotal == ^target)
             |> Ash.read()

    assert Enum.map(matched, & &1.reference) == ["F-USD"]

    other = H.m(900, :eur)

    assert {:ok, eur_matched} =
             H.invoice()
             |> Ash.Query.filter(subtotal == ^other)
             |> Ash.read()

    assert Enum.map(eur_matched, & &1.reference) == ["F-EUR"]

    missing = H.m(1, :jpy)

    assert {:ok, none} =
             H.invoice()
             |> Ash.Query.filter(subtotal == ^missing)
             |> Ash.read()

    assert none == []
  end
end

ExUnit.run()
"""


def _write_suite() -> None:
    with open(SUITE_PATH, "w", encoding="utf-8") as handle:
        handle.write(SUITE_EXS.lstrip("\n"))


def _parse(stdout: str) -> dict:
    results = {}
    for line in stdout.splitlines():
        if not line.startswith(MARKER):
            continue
        payload = line[len(MARKER) :]
        pieces = payload.split("@@")
        if len(pieces) < 3:
            continue
        name, status, encoded = pieces[0], pieces[1], pieces[2]
        try:
            detail = base64.b64decode(encoded).decode("utf-8", errors="replace")
        except Exception:  # pragma: no cover - defensive
            detail = encoded
        identifier = name.replace("test ", "", 1).split(" ", 1)[0]
        results[identifier] = (status, detail)
    return results


@pytest.fixture(scope="session")
def suite_results():
    assert os.path.isdir(PROJECT_DIR), f"Project directory {PROJECT_DIR} is missing."
    _write_suite()

    completed = subprocess.run(
        ["mix", "run", SUITE_PATH],
        cwd=PROJECT_DIR,
        capture_output=True,
        text=True,
        timeout=1800,
    )

    print(completed.stdout[-20000:])
    print(completed.stderr[-20000:])

    results = _parse(completed.stdout)

    if not results:
        pytest.fail(
            "The behaviour suite produced no results, which usually means the project "
            "failed to compile.\n"
            f"exit code: {completed.returncode}\n"
            f"stdout tail:\n{completed.stdout[-6000:]}\n"
            f"stderr tail:\n{completed.stderr[-6000:]}"
        )

    return results


def _check(results: dict, identifier: str) -> None:
    assert identifier in results, (
        f"Scenario {identifier} did not run. Scenarios reported: {sorted(results)}"
    )
    status, detail = results[identifier]
    assert status == "pass", f"Scenario {identifier} failed:\n{detail}"


def test_t01_currencies_and_exponents(suite_results):
    _check(suite_results, "T01")


def test_t02_constructors(suite_results):
    _check(suite_results, "T02")


def test_t03_canonical_string(suite_results):
    _check(suite_results, "T03")


def test_t04_addition_and_subtraction(suite_results):
    _check(suite_results, "T04")


def test_t05_multiplication(suite_results):
    _check(suite_results, "T05")


def test_t06_sum(suite_results):
    _check(suite_results, "T06")


def test_t07_comparison(suite_results):
    _check(suite_results, "T07")


def test_t08_cast_shapes_agree(suite_results):
    _check(suite_results, "T08")


def test_t09_canonical_string_casting(suite_results):
    _check(suite_results, "T09")


def test_t10_unknown_currency_errors(suite_results):
    _check(suite_results, "T10")


def test_t11_fractional_minor_units(suite_results):
    _check(suite_results, "T11")


def test_t12_invalid_format(suite_results):
    _check(suite_results, "T12")


def test_t13_equality(suite_results):
    _check(suite_results, "T13")


def test_t14_storage_type(suite_results):
    _check(suite_results, "T14")


def test_t15_storage_round_trip(suite_results):
    _check(suite_results, "T15")


def test_t16_array_and_nil_round_trip(suite_results):
    _check(suite_results, "T16")


def test_t17_invalid_stored_value(suite_results):
    _check(suite_results, "T17")


def test_t18_currencies_constraint(suite_results):
    _check(suite_results, "T18")


def test_t19_multiple_of_constraint(suite_results):
    _check(suite_results, "T19")


def test_t20_min_and_max_constraints(suite_results):
    _check(suite_results, "T20")


def test_t21_bound_currency_mismatch(suite_results):
    _check(suite_results, "T21")


def test_t22_constraint_ordering(suite_results):
    _check(suite_results, "T22")


def test_t23_array_cast_index(suite_results):
    _check(suite_results, "T23")


def test_t24_array_constraint_index(suite_results):
    _check(suite_results, "T24")


def test_t25_new_type_introspection(suite_results):
    _check(suite_results, "T25")


def test_t26_new_type_constraints(suite_results):
    _check(suite_results, "T26")


def test_t27_resource_round_trip(suite_results):
    _check(suite_results, "T27")


def test_t28_attribute_currency_constraint(suite_results):
    _check(suite_results, "T28")


def test_t29_resource_array_index(suite_results):
    _check(suite_results, "T29")


def test_t30_adjustment_currency_validation(suite_results):
    _check(suite_results, "T30")


def test_t31_apply_adjustment_appends(suite_results):
    _check(suite_results, "T31")


def test_t32_apply_adjustment_currency_mismatch(suite_results):
    _check(suite_results, "T32")


def test_t33_apply_adjustment_element_constraint(suite_results):
    _check(suite_results, "T33")


def test_t34_total_calculation(suite_results):
    _check(suite_results, "T34")


def test_t35_payments_aggregate_and_balance(suite_results):
    _check(suite_results, "T35")


def test_t36_derived_columns_are_not_writable(suite_results):
    _check(suite_results, "T36")


def test_t37_minor_unit_column_is_queryable(suite_results):
    _check(suite_results, "T37")


def test_t38_generic_action_returns_money(suite_results):
    _check(suite_results, "T38")


def test_t39_sorting_by_money(suite_results):
    _check(suite_results, "T39")


def test_t40_equality_filter(suite_results):
    _check(suite_results, "T40")
