defmodule Catering.Forms do
  @moduledoc """
  Facade that the LiveView layer uses to build, mutate, inspect and submit the
  nested catering order form.
  """

  @doc """
  1. new_order_form/0 — a blank create form for the order graph.
  """
  def new_order_form do
    AshPhoenix.Form.for_create(Catering.Orders.Order, :place,
      as: "order",
      id: "order"
    )
  end

  @doc """
  2. edit_order_form/1 — takes an order id and returns an update form for the stored order,
     including nested forms for its existing line items and their modifiers.
  """
  def edit_order_form(order_id) do
    order =
      Catering.Orders.Order
      |> Ash.get!(order_id, domain: Catering.Orders)
      |> Ash.load!([:customer, line_items: [:modifiers]], domain: Catering.Orders)

    sorted_line_items =
      order.line_items
      |> Enum.sort_by(& &1.position)
      |> Enum.map(fn line_item ->
        sorted_modifiers = Enum.sort_by(line_item.modifiers, & &1.position)
        %{line_item | modifiers: sorted_modifiers}
      end)

    order = %{order | line_items: sorted_line_items}

    AshPhoenix.Form.for_update(order, :revise,
      as: "order",
      id: "order"
    )
  end

  @doc """
  3. to_phoenix_form/1 — the %Phoenix.HTML.Form{} for a form.
  """
  def to_phoenix_form(form) do
    Phoenix.Component.to_form(form)
  end

  @doc """
  4. change/2 and change/3 — revalidate a form against a fresh parameter map,
     with an optional keyword list of validation options.
  """
  def change(form, params, opts \\ []) do
    AshPhoenix.Form.validate(form, params, opts)
  end

  @doc """
  5. add_nested/2 and add_nested/3 — add a nested form at a path, with an optional keyword list
     of options.
  """
  def add_nested(form, path, opts \\ []) do
    AshPhoenix.Form.add_form(form, path, opts)
  end

  @doc """
  6. remove_nested/2 — remove the nested form at a path.
  """
  def remove_nested(form, path) do
    AshPhoenix.Form.remove_form(form, path)
  end

  @doc """
  7. reorder/3 — reorder the nested list at a path, given the new ordering as a list of the
     current zero-based indices.
  """
  def reorder(form, path, order) do
    parsed_path = AshPhoenix.Form.parse_path!(form, path)
    AshPhoenix.Form.sort_forms(form, parsed_path, order)
  end

  @doc """
  8. move/3 — move the single nested form at a path one slot earlier (:up) or later (:down).
  """
  def move(form, path, direction) do
    parsed_path = AshPhoenix.Form.parse_path!(form, path)

    instruction =
      case direction do
        dir when dir in [:up, "up"] -> :decrement
        dir when dir in [:down, "down"] -> :increment
      end

    AshPhoenix.Form.sort_forms(form, parsed_path, instruction)
  end

  @doc """
  9. submitted_params/1 — the parameter map that would be sent to the underlying action.
  """
  def submitted_params(form) do
    AshPhoenix.Form.params(form)
  end

  @doc """
  10. hidden_inputs/2 — the hidden inputs required to render the form at a path.
  """
  def hidden_inputs(form, path) do
    case AshPhoenix.Form.get_form(form, path) do
      nil ->
        %{}

      target_form ->
        target_form
        |> AshPhoenix.Form.hidden_fields()
        |> Map.new(fn {key, val} -> {to_string(key), to_string(val)} end)
    end
  end

  @doc """
  11. error_map/1 — the user-facing errors of the whole form tree.
  """
  def error_map(form) do
    form
    |> force_errors()
    |> AshPhoenix.Form.errors(for_path: :all, format: :simple)
    |> Map.new(fn {path, errors} ->
      html_name = path_to_html_name(path)

      formatted_errors =
        errors
        |> Enum.map(fn {field, message} -> [to_string(field), message] end)
        |> Enum.sort()

      {html_name, formatted_errors}
    end)
  end

  @doc """
  12. raw_error_list/2 — the untranslated errors of the form at a path.
  """
  def raw_error_list(form, path) do
    parsed_path = AshPhoenix.Form.parse_path!(form, path)

    form
    |> force_errors()
    |> AshPhoenix.Form.errors(for_path: parsed_path, format: :raw)
    |> Enum.map(fn {field, {message, vars}} ->
      {field, message, vars}
    end)
    |> Enum.sort_by(fn {field, message, _vars} -> {field, message} end)
  end

  @doc """
  13. serialize/1 — a deterministic, plain-data snapshot of the whole form tree.
  """
  def serialize(form) do
    form
    |> force_errors()
    |> do_serialize()
  end

  @doc """
  14. save/2 — submit the form and persist the whole graph.
  """
  def save(form, params \\ nil) do
    case AshPhoenix.Form.submit(form, params: params) do
      {:ok, order} ->
        loaded_order =
          order
          |> Ash.load!([:customer, line_items: [:modifiers]], domain: Catering.Orders)

        sorted_line_items =
          loaded_order.line_items
          |> Enum.sort_by(& &1.position)
          |> Enum.map(fn line_item ->
            sorted_modifiers = Enum.sort_by(line_item.modifiers, & &1.position)
            %{line_item | modifiers: sorted_modifiers}
          end)

        {:ok, %{loaded_order | line_items: sorted_line_items}}

      {:error, form} ->
        {:error, form}
    end
  end

  # --- Private Helpers ---

  defp force_errors(form) do
    new_forms =
      Map.new(form.forms, fn {key, value} ->
        case value do
          nil ->
            {key, nil}

          [] ->
            {key, []}

          list when is_list(value) ->
            {key, Enum.map(list, &force_errors/1)}

          nested_form ->
            {key, force_errors(nested_form)}
        end
      end)

    %{form | errors: true, forms: new_forms}
  end

  defp path_to_html_name(trail) do
    Enum.reduce(trail, "order", fn
      elem, acc when is_integer(elem) ->
        acc <> "[#{elem}]"

      elem, acc ->
        acc <> "[#{elem}]"
    end)
  end

  defp do_serialize(form) do
    hidden =
      form
      |> AshPhoenix.Form.hidden_fields()
      |> Map.new(fn {key, val} -> {to_string(key), to_string(val)} end)
      |> Map.delete("_touched")

    fields =
      case form.resource do
        Catering.Orders.Order -> [:reference, :note]
        Catering.Orders.LineItem -> [:dish, :quantity]
        Catering.Orders.Modifier -> [:label, :surcharge_cents]
        Catering.Orders.Customer -> [:name, :email]
        Catering.Orders.DeliveryWindow -> [:label, :starts_at_minute, :ends_at_minute]
        Catering.Orders.CourierDrop -> [:street, :postcode]
        Catering.Orders.CounterPickup -> [:counter]
        _ -> []
      end

    values =
      fields
      |> Map.new(fn field ->
        val = AshPhoenix.Form.value(form, field)
        string_val = if is_nil(val), do: nil, else: to_string(val)
        {to_string(field), string_val}
      end)

    errors =
      form
      |> AshPhoenix.Form.errors(for_path: [], format: :simple)
      |> List.wrap()
      |> Enum.map(fn {field, message} -> [to_string(field), message] end)
      |> Enum.sort()

    nested =
      form.form_keys
      |> Keyword.keys()
      |> Map.new(fn key ->
        string_key = to_string(key)
        type = form.form_keys[key][:type] || :single
        val = Map.get(form.forms, key)

        serialized_val =
          case type do
            :single ->
              if is_nil(val) do
                nil
              else
                do_serialize(val)
              end

            :list ->
              if is_nil(val) do
                []
              else
                Enum.map(val, &do_serialize/1)
              end
          end

        {string_key, serialized_val}
      end)

    %{
      "name" => to_string(form.name),
      "id" => to_string(form.id),
      "type" => to_string(form.type),
      "resource" => inspect(form.resource),
      "valid" => form.valid?,
      "hidden" => hidden,
      "values" => values,
      "errors" => errors,
      "nested" => nested
    }
  end
end
