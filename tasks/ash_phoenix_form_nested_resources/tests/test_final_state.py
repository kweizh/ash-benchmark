import os
import re
import subprocess

import pytest

PROJECT_DIR = "/home/user/catering"
SUITE_PATH = "/tmp/harbor_final_suite.exs"
MARKER = "@@HARBOR@@"

HARBOR_SUITE_EXS = r"""
defmodule HarborFormatter do
  @moduledoc false
  use GenServer

  def init(_opts), do: {:ok, %{}}

  def handle_cast({:test_finished, %ExUnit.Test{} = test}, state) do
    status =
      case test.state do
        nil -> "pass"
        {:excluded, _} -> "skip"
        {:skipped, _} -> "skip"
        _ -> "fail"
      end

    detail =
      case test.state do
        nil ->
          ""

        {:failed, failures} ->
          ExUnit.Formatter.format_test_failure(test, failures, 1, 120, fn _, msg -> msg end)

        other ->
          inspect(other)
      end

    IO.puts("@@HARBOR@@#{test.name}@@#{status}@@#{Base.encode64(detail)}")
    {:noreply, state}
  end

  def handle_cast(_msg, state), do: {:noreply, state}
end

ExUnit.start(autorun: false, formatters: [HarborFormatter], seed: 0, colors: [enabled: false])

defmodule HarborFinalTest do
  use ExUnit.Case, async: false

  @forms Module.concat(["Catering", "Forms"])
  @orders Module.concat(["Catering", "Orders"])
  @order Module.concat(["Catering", "Orders", "Order"])
  @line_item Module.concat(["Catering", "Orders", "LineItem"])
  @modifier Module.concat(["Catering", "Orders", "Modifier"])
  @customer Module.concat(["Catering", "Orders", "Customer"])
  @delivery_window Module.concat(["Catering", "Orders", "DeliveryWindow"])
  @courier Module.concat(["Catering", "Orders", "CourierDrop"])

  # ---------------------------------------------------------------- helpers

  defp call(fun, args), do: apply(@forms, fun, args)

  defp new, do: call(:new_order_form, [])
  defp change(form, params, opts \\ []), do: call(:change, [form, params, opts])
  defp add(form, path, opts \\ []), do: call(:add_nested, [form, path, opts])
  defp remove(form, path), do: call(:remove_nested, [form, path])
  defp reorder(form, path, order), do: call(:reorder, [form, path, order])
  defp move(form, path, dir), do: call(:move, [form, path, dir])
  defp params(form), do: call(:submitted_params, [form])
  defp hidden(form, path), do: call(:hidden_inputs, [form, path])
  defp emap(form), do: call(:error_map, [form])
  defp raws(form, path), do: call(:raw_error_list, [form, path])
  defp ser(form), do: call(:serialize, [form])
  defp save(form), do: call(:save, [form, nil])
  defp save(form, p), do: call(:save, [form, p])

  defp dish_order(form) do
    ser(form)["nested"]["line_items"] |> Enum.map(& &1["values"]["dish"])
  end

  defp mod_labels(form, index) do
    ser(form)["nested"]["line_items"]
    |> Enum.at(index)
    |> Map.fetch!("nested")
    |> Map.get("modifiers", [])
    |> Enum.map(& &1["values"]["label"])
  end

  defp stored(resource), do: Ash.read!(resource)

  defp two_items(form) do
    form
    |> change(%{"reference" => "R-1"})
    |> add("order[line_items]", params: %{"dish" => "Soup", "quantity" => "2"})
    |> add("order[line_items]", params: %{"dish" => "Salad", "quantity" => "1"})
  end

  defp full_params do
    %{
      "reference" => "S-1",
      "note" => "hurry",
      "customer" => %{"name" => "Ada", "email" => "ada@example.com"},
      "line_items" => %{
        "0" => %{
          "dish" => "Soup",
          "quantity" => "2",
          "modifiers" => %{
            "0" => %{"label" => "extra", "surcharge_cents" => "50"},
            "1" => %{"label" => "hot", "surcharge_cents" => "10"}
          }
        },
        "1" => %{"dish" => "Salad", "quantity" => "1"}
      },
      "delivery_windows" => %{
        "0" => %{"label" => "am", "starts_at_minute" => "540", "ends_at_minute" => "600"}
      },
      "fulfillment" => %{"_union_type" => "courier", "street" => "1 Main", "postcode" => "AB1"}
    }
  end

  defp saved_order do
    {:ok, order} = new() |> change(full_params()) |> save()
    order
  end

  # --------------------------------------------------------- A. construction

  test "T01 new_order_form builds a create form for Order.place named order" do
    form = new()
    assert %AshPhoenix.Form{} = form
    assert form.resource == @order
    assert form.action == :place
    assert form.type == :create
    assert form.name == "order"
    assert form.id == "order"
    assert form.domain == @orders
  end

  test "T02 nested form keys are derived automatically from the action" do
    keys = new().form_keys |> Keyword.keys() |> Enum.uniq() |> Enum.sort()
    assert keys == [:customer, :delivery_windows, :fulfillment, :line_items]
  end

  test "T03 to_phoenix_form returns a Phoenix.HTML.Form wrapping the AshPhoenix form" do
    form = new()
    pf = call(:to_phoenix_form, [form])
    assert %Phoenix.HTML.Form{} = pf
    assert pf.name == "order"
    assert pf.id == "order"
    assert pf.source == form
    assert Phoenix.HTML.FormData.impl_for(form) == Phoenix.HTML.FormData.AshPhoenix.Form
  end

  test "T04 a fresh form submits only the form-type marker" do
    assert params(new()) == %{"_form_type" => "create"}
  end

  test "T05 serialize of a fresh form has the exact documented shape" do
    assert ser(new()) == %{
             "name" => "order",
             "id" => "order",
             "type" => "create",
             "resource" => "Catering.Orders.Order",
             "valid" => false,
             "hidden" => %{"_form_type" => "create"},
             "values" => %{"reference" => nil, "note" => nil},
             "errors" => [],
             "nested" => %{}
           }
  end

  test "T06 hidden_inputs reports the form type and the touched field list" do
    assert hidden(new(), "order") == %{"_form_type" => "create"}

    form = change(new(), %{"reference" => "R-1"})

    assert hidden(form, "order") == %{"_form_type" => "create", "_touched" => "reference"}
    assert ser(form)["hidden"] == %{"_form_type" => "create"}

    nested =
      form
      |> add("order[line_items]", params: %{"dish" => "Soup", "quantity" => "1"})

    assert hidden(nested, "order[line_items][0]")["_form_type"] == "create"
    assert Map.has_key?(hidden(nested, "order[line_items][0]"), "_touched")

    assert ser(nested)["nested"]["line_items"] |> Enum.at(0) |> Map.fetch!("hidden") == %{
             "_form_type" => "create"
           }
  end

  # ------------------------------------------------------- B. nested editing

  test "T07 add_nested appends list forms and names them by index" do
    form = two_items(new())

    assert params(form) == %{
             "_form_type" => "create",
             "_touched" => "line_items,reference",
             "reference" => "R-1",
             "line_items" => [
               %{
                 "_form_type" => "create",
                 "_touched" => "dish,quantity",
                 "dish" => "Soup",
                 "quantity" => "2"
               },
               %{
                 "_form_type" => "create",
                 "_touched" => "dish,quantity",
                 "dish" => "Salad",
                 "quantity" => "1"
               }
             ]
           }

    assert Map.keys(ser(form)["nested"]) == ["line_items"]

    names = ser(form)["nested"]["line_items"] |> Enum.map(& &1["name"])
    ids = ser(form)["nested"]["line_items"] |> Enum.map(& &1["id"])
    assert names == ["order[line_items][0]", "order[line_items][1]"]
    assert ids == ["order_line_items_0", "order_line_items_1"]
  end

  test "T08 add_nested works at a two-level-deep path" do
    form =
      two_items(new())
      |> add("order[line_items][0][modifiers]", params: %{"label" => "extra", "surcharge_cents" => "50"})
      |> add("order[line_items][0][modifiers]", params: %{"label" => "hot", "surcharge_cents" => "0"})

    assert params(form)["line_items"] |> Enum.at(0) |> Map.fetch!("modifiers") == [
             %{
               "_form_type" => "create",
               "_touched" => "label,surcharge_cents",
               "label" => "extra",
               "surcharge_cents" => "50"
             },
             %{
               "_form_type" => "create",
               "_touched" => "label,surcharge_cents",
               "label" => "hot",
               "surcharge_cents" => "0"
             }
           ]

    assert Map.has_key?(params(form)["line_items"] |> Enum.at(1), "modifiers") == false

    assert ser(form)["nested"]["line_items"]
           |> Enum.at(0)
           |> get_in(["nested", "modifiers"])
           |> Enum.map(& &1["name"]) ==
             ["order[line_items][0][modifiers][0]", "order[line_items][0][modifiers][1]"]
  end

  test "T09 add_nested honours the prepend option" do
    form =
      new()
      |> add("order[line_items]", params: %{"dish" => "Soup", "quantity" => "1"})
      |> add("order[line_items]", params: %{"dish" => "Salad", "quantity" => "1"}, prepend: true)

    assert dish_order(form) == ["Salad", "Soup"]
    assert ser(form)["nested"]["line_items"] |> Enum.map(& &1["name"]) ==
             ["order[line_items][0]", "order[line_items][1]"]
  end

  test "T10 remove_nested drops a single deep form and reindexes its siblings" do
    form =
      two_items(new())
      |> add("order[line_items][0][modifiers]", params: %{"label" => "extra", "surcharge_cents" => "50"})
      |> add("order[line_items][0][modifiers]", params: %{"label" => "hot", "surcharge_cents" => "0"})
      |> remove("order[line_items][0][modifiers][0]")

    assert mod_labels(form, 0) == ["hot"]

    assert ser(form)["nested"]["line_items"]
           |> Enum.at(0)
           |> get_in(["nested", "modifiers"])
           |> Enum.map(& &1["name"]) == ["order[line_items][0][modifiers][0]"]

    assert params(form)["line_items"] |> Enum.at(0) |> Map.fetch!("modifiers") |> length() == 1
  end

  test "T11 remove_nested drops the whole subtree of the removed form" do
    form =
      two_items(new())
      |> add("order[line_items][0][modifiers]", params: %{"label" => "extra", "surcharge_cents" => "50"})
      |> remove("order[line_items][0]")

    assert dish_order(form) == ["Salad"]
    assert ser(form)["nested"]["line_items"] |> Enum.map(& &1["name"]) == ["order[line_items][0]"]
    assert params(form)["line_items"] |> Enum.map(& &1["dish"]) == ["Salad"]
  end

  test "T12 embedded delivery windows are editable as nested list forms" do
    form =
      new()
      |> change(%{"reference" => "R-1"})
      |> add("order[delivery_windows]",
        params: %{"label" => "am", "starts_at_minute" => "540", "ends_at_minute" => "600"}
      )

    window = ser(form)["nested"]["delivery_windows"] |> Enum.at(0)
    assert window["name"] == "order[delivery_windows][0]"
    assert window["resource"] == "Catering.Orders.DeliveryWindow"
    assert window["type"] == "create"

    assert window["values"] == %{
             "label" => "am",
             "starts_at_minute" => "540",
             "ends_at_minute" => "600"
           }

    assert params(form)["delivery_windows"] |> Enum.at(0) |> Map.take(["label", "starts_at_minute", "ends_at_minute"]) ==
             %{"label" => "am", "starts_at_minute" => "540", "ends_at_minute" => "600"}
  end

  test "T13 union members are added by name and expose the union type as a hidden input" do
    form =
      new()
      |> change(%{"reference" => "R-1"})
      |> add("order[fulfillment]", params: %{"_union_type" => "courier", "street" => "1 Main", "postcode" => "AB1"})

    assert hidden(form, "order[fulfillment]") |> Map.take(["_form_type", "_union_type"]) == %{
             "_form_type" => "create",
             "_union_type" => "courier"
           }

    assert ser(form)["nested"]["fulfillment"]["resource"] == "Catering.Orders.CourierDrop"
    assert ser(form)["nested"]["fulfillment"]["values"] == %{"street" => "1 Main", "postcode" => "AB1"}
    assert params(form)["fulfillment"]["kind"] == "courier"
    assert params(form)["fulfillment"]["_union_type"] == "courier"
  end

  test "T14 replacing the union member swaps the nested form resource" do
    form =
      new()
      |> change(%{"reference" => "R-1"})
      |> add("order[fulfillment]", params: %{"_union_type" => "courier", "street" => "1 Main", "postcode" => "AB1"})
      |> remove("order[fulfillment]")
      |> add("order[fulfillment]", params: %{"_union_type" => "pickup", "counter" => "West"})

    assert ser(form)["nested"]["fulfillment"]["resource"] == "Catering.Orders.CounterPickup"
    assert ser(form)["nested"]["fulfillment"]["values"] == %{"counter" => "West"}
    assert params(form)["fulfillment"]["kind"] == "pickup"
  end

  # ------------------------------------------------------------- C. validate

  test "T15 error_map keys every failing form by its html name" do
    form =
      two_items(new())
      |> add("order[line_items][0][modifiers]", params: %{"label" => "x", "surcharge_cents" => "1"})
      |> change(%{
        "reference" => "",
        "line_items" => %{
          "0" => %{
            "dish" => "",
            "quantity" => "0",
            "modifiers" => %{"0" => %{"label" => "", "surcharge_cents" => "-1"}}
          },
          "1" => %{"dish" => "Salad", "quantity" => "1"}
        }
      })

    assert emap(form) == %{
             "order" => [["reference", "is required"]],
             "order[line_items][0]" => [["dish", "is required"], ["quantity", "must be positive"]],
             "order[line_items][0][modifiers][0]" => [
               ["label", "is required"],
               ["surcharge_cents", "must not be negative"]
             ]
           }

    refute form.valid?
  end

  test "T16 validating with errors disabled hides them but keeps the form invalid" do
    form = change(new(), %{"reference" => ""}, errors: false)
    assert emap(form) == %{}
    assert ser(form)["errors"] == []
    refute form.valid?
  end

  test "T17 revalidating with errors enabled reveals them again" do
    form =
      new()
      |> change(%{"reference" => ""}, errors: false)
      |> change(%{"reference" => ""})

    assert emap(form) == %{"order" => [["reference", "is required"]]}
    assert ser(form)["errors"] == [["reference", "is required"]]
  end

  test "T18 only_touched? restricts the submitted params to touched fields" do
    form = change(new(), %{"reference" => "T-1"})
    assert params(form) == %{"_form_type" => "create", "_touched" => "reference", "reference" => "T-1"}

    only = change(form, %{"reference" => "T-2", "note" => "ignored"}, only_touched?: true)
    assert params(only) == %{"_form_type" => "create", "_touched" => "reference", "reference" => "T-2"}

    both = change(form, %{"reference" => "T-3", "note" => "kept"})
    assert params(both)["note"] == "kept"
  end

  test "T19 raw_error_list exposes untranslated messages and substitution vars" do
    form =
      two_items(new())
      |> change(%{
        "reference" => "",
        "line_items" => %{
          "0" => %{"dish" => "", "quantity" => "0"},
          "1" => %{"dish" => "Salad", "quantity" => "1"}
        }
      })

    assert raws(form, "order") == [{:reference, "is required", []}]

    nested = raws(form, "order[line_items][0]")
    assert Enum.map(nested, fn {field, message, _vars} -> {field, message} end) ==
             [{:dish, "is required"}, {:quantity, "must be positive"}]

    {_, _, vars} = Enum.at(nested, 1)
    assert Keyword.get(vars, :greater_than) == 0
  end

  test "T20 errors nested two levels deep keep their own path" do
    form =
      new()
      |> change(%{"reference" => "R-1"})
      |> add("order[line_items]", params: %{"dish" => "Soup", "quantity" => "1"})
      |> add("order[line_items][0][modifiers]", params: %{"label" => "", "surcharge_cents" => "0"})
      |> change(%{
        "reference" => "R-1",
        "line_items" => %{
          "0" => %{"dish" => "Soup", "quantity" => "1", "modifiers" => %{"0" => %{"label" => "", "surcharge_cents" => "0"}}}
        }
      })

    assert emap(form) == %{"order[line_items][0][modifiers][0]" => [["label", "is required"]]}
    assert raws(form, "order[line_items][0][modifiers][0]") == [{:label, "is required", []}]
  end

  test "T21 embedded window validation failures are reported on the window form" do
    form =
      new()
      |> change(%{"reference" => "R-1"})
      |> add("order[delivery_windows]",
        params: %{"label" => "am", "starts_at_minute" => "600", "ends_at_minute" => "540"}
      )
      |> change(%{
        "reference" => "R-1",
        "delivery_windows" => %{
          "0" => %{"label" => "am", "starts_at_minute" => "600", "ends_at_minute" => "540"}
        }
      })

    assert emap(form) == %{
             "order[delivery_windows][0]" => [["ends_at_minute", "must be after the start"]]
           }
  end

  test "T22 union member validation failures are reported on the union form" do
    form =
      new()
      |> change(%{"reference" => "R-1"})
      |> add("order[fulfillment]", params: %{"_union_type" => "courier"})
      |> change(%{
        "reference" => "R-1",
        "fulfillment" => %{"_union_type" => "courier", "street" => "", "postcode" => ""}
      })

    assert emap(form) == %{
             "order[fulfillment]" => [["postcode", "is required"], ["street", "is required"]]
           }
  end

  # ----------------------------------------------------- D. param round-trip

  test "T23 the submitted params rebuild an identical form tree" do
    form =
      two_items(new())
      |> add("order[line_items][0][modifiers]", params: %{"label" => "extra", "surcharge_cents" => "50"})

    rebuilt = change(new(), params(form))
    assert params(rebuilt) == params(form)
    assert ser(rebuilt) == ser(form)
  end

  test "T24 the _add_ checkbox param appends an empty nested form" do
    form =
      change(new(), %{
        "reference" => "R-1",
        "_add_line_items" => "end",
        "line_items" => %{"0" => %{"dish" => "Soup", "quantity" => "1"}}
      })

    assert dish_order(form) == ["Soup", nil]
  end

  test "T25 the _drop_ checkbox param removes the nested form at that index" do
    form =
      change(new(), %{
        "reference" => "R-1",
        "_drop_line_items" => ["0"],
        "line_items" => %{
          "0" => %{"dish" => "Soup", "quantity" => "1"},
          "1" => %{"dish" => "Salad", "quantity" => "1"}
        }
      })

    assert dish_order(form) == ["Salad"]
  end

  test "T26 the _sort_ checkbox param reorders the nested forms" do
    form =
      change(new(), %{
        "reference" => "R-1",
        "_sort_line_items" => ["1", "0"],
        "line_items" => %{
          "0" => %{"dish" => "Soup", "quantity" => "1"},
          "1" => %{"dish" => "Salad", "quantity" => "1"}
        }
      })

    assert dish_order(form) == ["Salad", "Soup"]
  end

  test "T27 a read-typed customer form survives a params round-trip" do
    customer = Ash.create!(@customer, %{name: "Pat", email: "pat@example.com"}, action: :register)

    form =
      new()
      |> change(%{"reference" => "R-1"})
      |> add("order[customer]", type: :read, params: %{"id" => customer.id})

    rebuilt = change(form, params(form))

    assert ser(rebuilt)["nested"]["customer"]["type"] == "read"
    assert ser(rebuilt)["nested"]["customer"]["name"] == "order[customer]"
    assert hidden(rebuilt, "order[customer]")["_form_type"] == "read"
    assert params(rebuilt)["customer"]["id"] == customer.id
    assert params(rebuilt)["customer"]["_form_type"] == "read"
  end

  test "T28 add_nested with type read produces a read-typed nested form" do
    customer = Ash.create!(@customer, %{name: "Pat", email: "pat@example.com"}, action: :register)

    form =
      new()
      |> change(%{"reference" => "R-1"})
      |> add("order[customer]", type: :read, params: %{"id" => customer.id})

    assert ser(form)["nested"]["customer"]["type"] == "read"
    assert params(form)["customer"] == %{
             "_form_type" => "read",
             "_touched" => "id",
             "id" => customer.id
           }
  end

  # -------------------------------------------------------------- E. sorting

  test "T29 reorder rearranges a top-level nested list and marks it for submission" do
    form = reorder(two_items(new()), "order[line_items]", [1, 0])

    assert dish_order(form) == ["Salad", "Soup"]
    assert ser(form)["nested"]["line_items"] |> Enum.map(& &1["name"]) ==
             ["order[line_items][0]", "order[line_items][1]"]

    assert params(form)["line_items"] |> Enum.map(& &1["dish"]) == ["Salad", "Soup"]
  end

  test "T30 reorder rearranges a list nested inside another list form" do
    form =
      two_items(new())
      |> add("order[line_items][0][modifiers]", params: %{"label" => "extra", "surcharge_cents" => "50"})
      |> add("order[line_items][0][modifiers]", params: %{"label" => "hot", "surcharge_cents" => "0"})
      |> reorder("order[line_items][0][modifiers]", [1, 0])

    assert mod_labels(form, 0) == ["hot", "extra"]

    assert ser(form)["nested"]["line_items"]
           |> Enum.at(0)
           |> get_in(["nested", "modifiers"])
           |> Enum.map(& &1["name"]) ==
             ["order[line_items][0][modifiers][0]", "order[line_items][0][modifiers][1]"]

    assert params(form)["line_items"] |> Enum.at(0) |> Map.fetch!("modifiers") |> Enum.map(& &1["label"]) ==
             ["hot", "extra"]
  end

  test "T31 move shifts a single nested form up or down" do
    form = two_items(new())

    assert dish_order(move(form, "order[line_items][1]", :up)) == ["Salad", "Soup"]
    assert dish_order(move(form, "order[line_items][0]", :down)) == ["Salad", "Soup"]
    assert params(move(form, "order[line_items][1]", :up))["line_items"] |> Enum.map(& &1["dish"]) ==
             ["Salad", "Soup"]
  end

  test "T32 move is a no-op at the boundaries and works on deep paths" do
    form =
      two_items(new())
      |> add("order[line_items][0][modifiers]", params: %{"label" => "extra", "surcharge_cents" => "50"})
      |> add("order[line_items][0][modifiers]", params: %{"label" => "hot", "surcharge_cents" => "0"})

    assert dish_order(move(form, "order[line_items][0]", :up)) == ["Soup", "Salad"]
    assert dish_order(move(form, "order[line_items][1]", :down)) == ["Soup", "Salad"]
    assert mod_labels(move(form, "order[line_items][0][modifiers][1]", :up), 0) == ["hot", "extra"]
    assert mod_labels(move(form, "order[line_items][0][modifiers][0]", :down), 0) == ["hot", "extra"]
  end

  # ------------------------------------------------------------ F. submitting

  test "T33 save persists the whole graph in one call" do
    {:ok, order} = new() |> change(full_params()) |> save()

    assert order.reference == "S-1"
    assert order.note == "hurry"

    assert Enum.map(order.line_items, &{&1.dish, &1.quantity, &1.position}) == [
             {"Soup", 2, 0},
             {"Salad", 1, 1}
           ]

    assert order.line_items
           |> Enum.at(0)
           |> Map.fetch!(:modifiers)
           |> Enum.map(&{&1.label, &1.surcharge_cents, &1.position}) == [{"extra", 50, 0}, {"hot", 10, 1}]

    assert order.line_items |> Enum.at(1) |> Map.fetch!(:modifiers) == []
    assert length(stored(@line_item)) == 2
    assert length(stored(@modifier)) == 2
  end

  test "T34 save stores the embedded delivery windows and the union member" do
    order = saved_order()

    assert Enum.map(order.delivery_windows, &{&1.label, &1.starts_at_minute, &1.ends_at_minute}) ==
             [{"am", 540, 600}]

    assert %Ash.Union{type: :courier, value: value} = order.fulfillment
    assert value.__struct__ == @courier
    assert {value.street, value.postcode} == {"1 Main", "AB1"}
  end

  test "T35 an inline customer form creates exactly one customer and links it" do
    order = saved_order()

    customers = stored(@customer)
    assert length(customers) == 1
    assert hd(customers).name == "Ada"
    assert hd(customers).email == "ada@example.com"
    assert order.customer.id == hd(customers).id
    assert order.customer_id == hd(customers).id
  end

  test "T36 a read-typed customer form relates the existing customer without creating one" do
    customer = Ash.create!(@customer, %{name: "Pat", email: "pat@example.com"}, action: :register)

    {:ok, order} =
      new()
      |> add("order[customer]", type: :read, params: %{"id" => customer.id})
      |> change(%{"reference" => "R-7", "customer" => %{"_form_type" => "read", "id" => customer.id}})
      |> save()

    assert order.customer_id == customer.id
    assert length(stored(@customer)) == 1
  end

  test "T37 a failed save returns the form, writes nothing and stays reusable" do
    form =
      new()
      |> change(%{
        "reference" => "BAD",
        "customer" => %{"name" => "Bob", "email" => "bob@example.com"},
        "line_items" => %{"0" => %{"dish" => "Stew", "quantity" => "0"}}
      })

    assert {:error, returned} = save(form)
    assert %AshPhoenix.Form{} = returned
    assert emap(returned) == %{"order[line_items][0]" => [["quantity", "must be positive"]]}
    assert returned.submitted_once?
    assert stored(@order) == []
    assert stored(@line_item) == []
    assert stored(@customer) == []

    {:ok, order} =
      save(returned, %{
        "reference" => "BAD",
        "customer" => %{"name" => "Bob", "email" => "bob@example.com"},
        "line_items" => %{"0" => %{"dish" => "Stew", "quantity" => "3"}}
      })

    assert Enum.map(order.line_items, &{&1.dish, &1.quantity}) == [{"Stew", 3}]
    assert length(stored(@order)) == 1
  end

  test "T38 save accepts params and validates them before submitting" do
    assert {:ok, order} = save(new(), full_params())
    assert order.reference == "S-1"
    assert length(order.line_items) == 2
  end

  # ----------------------------------------------------------- G. edit flows

  test "T39 edit_order_form builds update forms in stored order with hidden ids" do
    order = saved_order()
    form = call(:edit_order_form, [order.id])

    assert form.type == :update
    assert form.name == "order"
    assert hidden(form, "order") == %{"_form_type" => "update", "id" => order.id}
    assert ser(form)["type"] == "update"
    assert ser(form)["values"] == %{"reference" => "S-1", "note" => "hurry"}
    assert Map.keys(ser(form)["nested"]) |> Enum.sort() == ["delivery_windows", "fulfillment", "line_items"]

    assert dish_order(form) == ["Soup", "Salad"]
    assert mod_labels(form, 0) == ["extra", "hot"]
    assert mod_labels(form, 1) == []

    ids = ser(form)["nested"]["line_items"] |> Enum.map(& &1["hidden"]["id"])
    assert ids == Enum.map(order.line_items, & &1.id)
    assert ser(form)["nested"]["line_items"] |> Enum.map(& &1["type"]) == ["update", "update"]
  end

  test "T40 edit_order_form orders nested forms by stored position, not by storage order" do
    params =
      full_params()
      |> Map.put("line_items", %{
        "0" => %{"dish" => "A", "quantity" => "1"},
        "1" => %{"dish" => "B", "quantity" => "1"},
        "2" => %{"dish" => "C", "quantity" => "1"},
        "3" => %{"dish" => "D", "quantity" => "1"},
        "4" => %{"dish" => "E", "quantity" => "1"}
      })

    {:ok, order} = save(new(), params)
    assert Enum.map(order.line_items, & &1.dish) == ["A", "B", "C", "D", "E"]

    reordered = reorder(call(:edit_order_form, [order.id]), "order[line_items]", [4, 3, 2, 1, 0])
    {:ok, saved} = save(reordered)

    assert Enum.map(saved.line_items, &{&1.dish, &1.position}) == [
             {"E", 0},
             {"D", 1},
             {"C", 2},
             {"B", 3},
             {"A", 4}
           ]

    assert dish_order(call(:edit_order_form, [saved.id])) == ["E", "D", "C", "B", "A"]
  end

  test "T41 removing a nested form from an edit form destroys that record on save" do
    order = saved_order()
    salad_id = order.line_items |> Enum.at(1) |> Map.fetch!(:id)

    {:ok, saved} =
      call(:edit_order_form, [order.id])
      |> remove("order[line_items][1]")
      |> save()

    assert Enum.map(saved.line_items, & &1.dish) == ["Soup"]
    assert length(stored(@line_item)) == 1
    refute Enum.any?(stored(@line_item), &(&1.id == salad_id))
    assert length(stored(@modifier)) == 2
  end

  test "T42 removing a deep nested form destroys only that record" do
    order = saved_order()

    {:ok, saved} =
      call(:edit_order_form, [order.id])
      |> remove("order[line_items][0][modifiers][0]")
      |> save()

    assert saved.line_items |> Enum.at(0) |> Map.fetch!(:modifiers) |> Enum.map(& &1.label) == ["hot"]
    assert length(stored(@modifier)) == 1
    assert length(stored(@line_item)) == 2
  end

  test "T43 reordering a deep nested list on an edit form renumbers its positions" do
    order = saved_order()

    {:ok, saved} =
      call(:edit_order_form, [order.id])
      |> reorder("order[line_items][0][modifiers]", [1, 0])
      |> save()

    assert saved.line_items |> Enum.at(0) |> Map.fetch!(:modifiers) |> Enum.map(&{&1.label, &1.position}) ==
             [{"hot", 0}, {"extra", 1}]

    assert length(stored(@modifier)) == 2
  end

  test "T44 adding a nested form to an existing record on an edit form creates it" do
    order = saved_order()

    {:ok, saved} =
      call(:edit_order_form, [order.id])
      |> add("order[line_items][1][modifiers]", params: %{"label" => "late", "surcharge_cents" => "5"})
      |> save()

    assert saved.line_items |> Enum.at(1) |> Map.fetch!(:modifiers) |> Enum.map(&{&1.label, &1.surcharge_cents, &1.position}) ==
             [{"late", 5, 0}]

    assert length(stored(@modifier)) == 3
  end

  test "T45 an edit form round-trips its own submitted params" do
    order = saved_order()
    form = call(:edit_order_form, [order.id])
    touched = change(form, params(form))

    assert dish_order(touched) == ["Soup", "Salad"]
    assert {:ok, saved} = save(touched)
    assert Enum.map(saved.line_items, &{&1.dish, &1.position}) == [{"Soup", 0}, {"Salad", 1}]
    assert length(stored(@line_item)) == 2
    assert length(stored(@modifier)) == 2
  end
end

ExUnit.run()
"""


def _run_suite():
    with open(SUITE_PATH, "w") as handle:
        handle.write(HARBOR_SUITE_EXS.lstrip("\n"))

    env = os.environ.copy()
    env["MIX_ENV"] = "dev"
    env.pop("MIX_TARGET", None)

    process = subprocess.run(
        ["mix", "run", SUITE_PATH],
        cwd=PROJECT_DIR,
        capture_output=True,
        text=True,
        timeout=1800,
        env=env,
    )

    output = (process.stdout or "") + "\n" + (process.stderr or "")
    results = {}
    for line in output.splitlines():
        if not line.startswith(MARKER):
            continue
        parts = line.split("@@")
        # ["", "HARBOR", "<name>", "<status>", "<base64 detail>"]
        if len(parts) < 5:
            continue
        name = parts[2].strip()
        status = parts[3].strip()
        detail = parts[4].strip()
        match = re.match(r"^test\s+(T\d+)\b", name)
        if match:
            results[match.group(1)] = (status, detail)

    return results, output


@pytest.fixture(scope="session")
def suite_results():
    results, output = _run_suite()
    if not results:
        pytest.fail(
            "The Elixir verification suite produced no results. "
            "The project most likely failed to compile. Output tail:\n"
            + "\n".join(output.splitlines()[-80:])
        )
    return results, output


def _assert_scenario(suite_results, scenario_id, description):
    results, output = suite_results
    if scenario_id not in results:
        pytest.fail(
            f"Scenario {scenario_id} ({description}) did not run. Suite output tail:\n"
            + "\n".join(output.splitlines()[-80:])
        )

    status, detail = results[scenario_id]
    if status != "pass":
        import base64

        try:
            decoded = base64.b64decode(detail).decode("utf-8", "replace")
        except Exception:  # pragma: no cover - defensive
            decoded = detail
        pytest.fail(f"Scenario {scenario_id} ({description}) failed:\n{decoded}")


def test_t01_new_order_form_builds_a_create_form_for_order_place_named_order(suite_results):
    _assert_scenario(suite_results, "T01", "new_order_form builds a create form for Order.place named order")

def test_t02_nested_form_keys_are_derived_automatically_from_the_action(suite_results):
    _assert_scenario(suite_results, "T02", "nested form keys are derived automatically from the action")

def test_t03_to_phoenix_form_returns_a_phoenix_html_form_wrapping_the_ashphoenix_fo(suite_results):
    _assert_scenario(suite_results, "T03", "to_phoenix_form returns a Phoenix.HTML.Form wrapping the AshPhoenix form")

def test_t04_a_fresh_form_submits_only_the_form_type_marker(suite_results):
    _assert_scenario(suite_results, "T04", "a fresh form submits only the form-type marker")

def test_t05_serialize_of_a_fresh_form_has_the_exact_documented_shape(suite_results):
    _assert_scenario(suite_results, "T05", "serialize of a fresh form has the exact documented shape")

def test_t06_hidden_inputs_reports_the_form_type_and_the_touched_field_list(suite_results):
    _assert_scenario(suite_results, "T06", "hidden_inputs reports the form type and the touched field list")

def test_t07_add_nested_appends_list_forms_and_names_them_by_index(suite_results):
    _assert_scenario(suite_results, "T07", "add_nested appends list forms and names them by index")

def test_t08_add_nested_works_at_a_two_level_deep_path(suite_results):
    _assert_scenario(suite_results, "T08", "add_nested works at a two-level-deep path")

def test_t09_add_nested_honours_the_prepend_option(suite_results):
    _assert_scenario(suite_results, "T09", "add_nested honours the prepend option")

def test_t10_remove_nested_drops_a_single_deep_form_and_reindexes_its_siblings(suite_results):
    _assert_scenario(suite_results, "T10", "remove_nested drops a single deep form and reindexes its siblings")

def test_t11_remove_nested_drops_the_whole_subtree_of_the_removed_form(suite_results):
    _assert_scenario(suite_results, "T11", "remove_nested drops the whole subtree of the removed form")

def test_t12_embedded_delivery_windows_are_editable_as_nested_list_forms(suite_results):
    _assert_scenario(suite_results, "T12", "embedded delivery windows are editable as nested list forms")

def test_t13_union_members_are_added_by_name_and_expose_the_union_type_as_a_hidden_(suite_results):
    _assert_scenario(suite_results, "T13", "union members are added by name and expose the union type as a hidden input")

def test_t14_replacing_the_union_member_swaps_the_nested_form_resource(suite_results):
    _assert_scenario(suite_results, "T14", "replacing the union member swaps the nested form resource")

def test_t15_error_map_keys_every_failing_form_by_its_html_name(suite_results):
    _assert_scenario(suite_results, "T15", "error_map keys every failing form by its html name")

def test_t16_validating_with_errors_disabled_hides_them_but_keeps_the_form_invalid(suite_results):
    _assert_scenario(suite_results, "T16", "validating with errors disabled hides them but keeps the form invalid")

def test_t17_revalidating_with_errors_enabled_reveals_them_again(suite_results):
    _assert_scenario(suite_results, "T17", "revalidating with errors enabled reveals them again")

def test_t18_only_touched_restricts_the_submitted_params_to_touched_fields(suite_results):
    _assert_scenario(suite_results, "T18", "only_touched? restricts the submitted params to touched fields")

def test_t19_raw_error_list_exposes_untranslated_messages_and_substitution_vars(suite_results):
    _assert_scenario(suite_results, "T19", "raw_error_list exposes untranslated messages and substitution vars")

def test_t20_errors_nested_two_levels_deep_keep_their_own_path(suite_results):
    _assert_scenario(suite_results, "T20", "errors nested two levels deep keep their own path")

def test_t21_embedded_window_validation_failures_are_reported_on_the_window_form(suite_results):
    _assert_scenario(suite_results, "T21", "embedded window validation failures are reported on the window form")

def test_t22_union_member_validation_failures_are_reported_on_the_union_form(suite_results):
    _assert_scenario(suite_results, "T22", "union member validation failures are reported on the union form")

def test_t23_the_submitted_params_rebuild_an_identical_form_tree(suite_results):
    _assert_scenario(suite_results, "T23", "the submitted params rebuild an identical form tree")

def test_t24_the_add_checkbox_param_appends_an_empty_nested_form(suite_results):
    _assert_scenario(suite_results, "T24", "the _add_ checkbox param appends an empty nested form")

def test_t25_the_drop_checkbox_param_removes_the_nested_form_at_that_index(suite_results):
    _assert_scenario(suite_results, "T25", "the _drop_ checkbox param removes the nested form at that index")

def test_t26_the_sort_checkbox_param_reorders_the_nested_forms(suite_results):
    _assert_scenario(suite_results, "T26", "the _sort_ checkbox param reorders the nested forms")

def test_t27_a_read_typed_customer_form_survives_a_params_round_trip(suite_results):
    _assert_scenario(suite_results, "T27", "a read-typed customer form survives a params round-trip")

def test_t28_add_nested_with_type_read_produces_a_read_typed_nested_form(suite_results):
    _assert_scenario(suite_results, "T28", "add_nested with type read produces a read-typed nested form")

def test_t29_reorder_rearranges_a_top_level_nested_list_and_marks_it_for_submission(suite_results):
    _assert_scenario(suite_results, "T29", "reorder rearranges a top-level nested list and marks it for submission")

def test_t30_reorder_rearranges_a_list_nested_inside_another_list_form(suite_results):
    _assert_scenario(suite_results, "T30", "reorder rearranges a list nested inside another list form")

def test_t31_move_shifts_a_single_nested_form_up_or_down(suite_results):
    _assert_scenario(suite_results, "T31", "move shifts a single nested form up or down")

def test_t32_move_is_a_no_op_at_the_boundaries_and_works_on_deep_paths(suite_results):
    _assert_scenario(suite_results, "T32", "move is a no-op at the boundaries and works on deep paths")

def test_t33_save_persists_the_whole_graph_in_one_call(suite_results):
    _assert_scenario(suite_results, "T33", "save persists the whole graph in one call")

def test_t34_save_stores_the_embedded_delivery_windows_and_the_union_member(suite_results):
    _assert_scenario(suite_results, "T34", "save stores the embedded delivery windows and the union member")

def test_t35_an_inline_customer_form_creates_exactly_one_customer_and_links_it(suite_results):
    _assert_scenario(suite_results, "T35", "an inline customer form creates exactly one customer and links it")

def test_t36_a_read_typed_customer_form_relates_the_existing_customer_without_creat(suite_results):
    _assert_scenario(suite_results, "T36", "a read-typed customer form relates the existing customer without creating one")

def test_t37_a_failed_save_returns_the_form_writes_nothing_and_stays_reusable(suite_results):
    _assert_scenario(suite_results, "T37", "a failed save returns the form, writes nothing and stays reusable")

def test_t38_save_accepts_params_and_validates_them_before_submitting(suite_results):
    _assert_scenario(suite_results, "T38", "save accepts params and validates them before submitting")

def test_t39_edit_order_form_builds_update_forms_in_stored_order_with_hidden_ids(suite_results):
    _assert_scenario(suite_results, "T39", "edit_order_form builds update forms in stored order with hidden ids")

def test_t40_edit_order_form_orders_nested_forms_by_stored_position_not_by_storage_(suite_results):
    _assert_scenario(suite_results, "T40", "edit_order_form orders nested forms by stored position, not by storage order")

def test_t41_removing_a_nested_form_from_an_edit_form_destroys_that_record_on_save(suite_results):
    _assert_scenario(suite_results, "T41", "removing a nested form from an edit form destroys that record on save")

def test_t42_removing_a_deep_nested_form_destroys_only_that_record(suite_results):
    _assert_scenario(suite_results, "T42", "removing a deep nested form destroys only that record")

def test_t43_reordering_a_deep_nested_list_on_an_edit_form_renumbers_its_positions(suite_results):
    _assert_scenario(suite_results, "T43", "reordering a deep nested list on an edit form renumbers its positions")

def test_t44_adding_a_nested_form_to_an_existing_record_on_an_edit_form_creates_it(suite_results):
    _assert_scenario(suite_results, "T44", "adding a nested form to an existing record on an edit form creates it")

def test_t45_an_edit_form_round_trips_its_own_submitted_params(suite_results):
    _assert_scenario(suite_results, "T45", "an edit form round-trips its own submitted params")
