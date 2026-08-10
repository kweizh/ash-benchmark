Application.ensure_all_started(:catering)

# Create an order
form = AshPhoenix.Form.for_create(Catering.Orders.Order, :place,
  as: "order", domain: Catering.Orders, forms: [auto?: true], errors: false
)
form = AshPhoenix.Form.add_form(form, "order[line_items]", params: %{"dish" => "Pizza", "quantity" => "2"})
form = AshPhoenix.Form.add_form(form, "order[line_items]", params: %{"dish" => "Salad", "quantity" => "3"})
form = AshPhoenix.Form.add_form(form, "order[line_items][0][modifiers]", params: %{"label" => "Extra cheese", "surcharge_cents" => "100"})
form = AshPhoenix.Form.add_form(form, "order[customer]", params: %{"name" => "Alice", "email" => "alice@example.com"})
form = AshPhoenix.Form.add_form(form, "order[delivery_windows]", params: %{"label" => "Lunch", "starts_at_minute" => "720", "ends_at_minute" => "780"})
form = AshPhoenix.Form.add_form(form, "order[fulfillment]", params: %{"_union_type" => "courier", "street" => "1 Main St", "postcode" => "12345"})
form = AshPhoenix.Form.validate(form, AshPhoenix.Form.params(form, transform?: false, hidden?: true) |> Map.merge(%{"reference" => "ORD-1", "note" => "Please ring bell"}), errors: false)
{:ok, order} = AshPhoenix.Form.submit(form, params: nil)
order_id = order.id

# Load and build edit form
order = Ash.get!(Catering.Orders.Order, order_id)
order = Ash.load!(order, [:customer, line_items: [:modifiers]])
order = %{order | line_items: order.line_items |> Enum.sort_by(& &1.position) |> Enum.map(fn li -> %{li | modifiers: Enum.sort_by(li.modifiers, & &1.position)} end)}

eform = AshPhoenix.Form.for_update(order, :revise,
  as: "order", domain: Catering.Orders, forms: [auto?: true], errors: false
)

# Check fulfillment form
ff = eform.forms[:fulfillment]
IO.puts("=== fulfillment form ===")
IO.inspect(ff.name, label: "name")
IO.inspect(ff.resource, label: "resource")
IO.inspect(ff.type, label: "type")
IO.inspect(ff.data, label: "data")
IO.inspect(ff.params, label: "params")
IO.inspect(AshPhoenix.Form.value(ff, :street), label: "value street")
IO.inspect(AshPhoenix.Form.value(ff, :postcode), label: "value postcode")
IO.inspect(AshPhoenix.Form.hidden_fields(ff), label: "hidden")

IO.puts("\n=== fulfillment params (only_touched: false) ===")
IO.inspect(AshPhoenix.Form.params(ff, only_touched?: false))

# Validate and check
p = AshPhoenix.Form.params(eform, only_touched?: false)
eform2 = AshPhoenix.Form.validate(eform, p, errors: false)

ff2 = eform2.forms[:fulfillment]
IO.puts("\n=== fulfillment form after validate ===")
IO.inspect(ff2.params, label: "params")
IO.inspect(AshPhoenix.Form.value(ff2, :street), label: "value street")
IO.inspect(AshPhoenix.Form.value(ff2, :postcode), label: "value postcode")

IO.puts("\n=== full params after validate ===")
IO.inspect(AshPhoenix.Form.params(eform2))

# Submit and check fulfillment
case AshPhoenix.Form.submit(eform2, params: nil) do
  {:ok, order2} ->
    IO.puts("\n=== After submit ===")
    IO.inspect(order2.fulfillment, label: "fulfillment")
    IO.inspect(order2.reference, label: "reference")
    IO.inspect(order2.note, label: "note")
    IO.inspect(order2.delivery_windows, label: "delivery_windows")
  {:error, eform3} ->
    IO.puts("Failed!")
    IO.inspect(AshPhoenix.Form.errors(eform3, for_path: :all))
end

# Test removing a line item
IO.puts("\n=== Test remove line_item[1] ===")
eform4 = AshPhoenix.Form.remove_form(eform2, "order[line_items][1]")
IO.inspect(eform4.forms[:line_items] |> Enum.map(&{&1.name, &1.data.dish}), label: "after remove")
IO.inspect(AshPhoenix.Form.params(eform4)["line_items"] |> Enum.map(& &1["dish"]), label: "params dishes")

case AshPhoenix.Form.submit(eform4, params: nil) do
  {:ok, order3} ->
    IO.puts("Removed and saved!")
    order3 = Ash.load!(order3, [:customer, line_items: [:modifiers]])
    for li <- order3.line_items |> Enum.sort_by(& &1.position) do
      IO.inspect({li.dish, li.quantity, li.position, Enum.map(li.modifiers, & &1.label)})
    end
  {:error, eform5} ->
    IO.puts("Failed!")
    IO.inspect(AshPhoenix.Form.errors(eform5, for_path: :all))
end
