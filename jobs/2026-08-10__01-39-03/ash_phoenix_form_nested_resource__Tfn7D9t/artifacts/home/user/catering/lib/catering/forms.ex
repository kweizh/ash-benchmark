defmodule Catering.Forms do
  @moduledoc """
  Facade that the LiveView layer uses to build, mutate, inspect and submit the
  nested catering order form.

  This module is a thin, faithful wrapper around `AshPhoenix.Form`. All the
  nested-form wiring (line items, their modifiers, delivery windows, the
  fulfillment union and the customer) is inferred automatically by
  `AshPhoenix.Form` from the `manage_relationship`/embedded/union usage on
  `Catering.Orders.Order`'s `:place` and `:revise` actions, so this module
  does not need to (and must not) configure any of that by hand.
  """

  alias AshPhoenix.Form
  alias Catering.Orders.{CounterPickup, CourierDrop, Customer, DeliveryWindow, LineItem, Modifier, Order}

  @root_name "order"

  @value_fields %{
    Order => [:reference, :note],
    LineItem => [:dish, :quantity],
    Modifier => [:label, :surcharge_cents],
    Customer => [:name, :email],
    DeliveryWindow => [:label, :starts_at_minute, :ends_at_minute],
    CourierDrop => [:street, :postcode],
    CounterPickup => [:counter]
  }

  # ---------------------------------------------------------------------
  # Building forms
  # ---------------------------------------------------------------------

  @doc "A blank create form for the order graph."
  @spec new_order_form() :: Form.t()
  def new_order_form do
    Form.for_create(Order, :place, as: @root_name)
  end

  @doc """
  An update form for the stored order with the given id, including nested
  forms for its existing line items and their modifiers, presented in
  ascending stored `position`.
  """
  @spec edit_order_form(term()) :: Form.t()
  def edit_order_form(order_id) do
    order_id
    |> load_order_for_edit!()
    |> Form.for_update(:revise, as: @root_name)
  end

  defp load_order_for_edit!(order_id) do
    modifiers_query = Ash.Query.sort(Modifier, :position)

    line_items_query =
      LineItem
      |> Ash.Query.sort(:position)
      |> Ash.Query.load(modifiers: modifiers_query)

    Ash.get!(Order, order_id, load: [line_items: line_items_query])
  end

  @doc "The `%Phoenix.HTML.Form{}` for a form."
  @spec to_phoenix_form(Form.t()) :: Phoenix.HTML.Form.t()
  def to_phoenix_form(form), do: Phoenix.HTML.FormData.to_form(form, [])

  # ---------------------------------------------------------------------
  # Mutating forms
  # ---------------------------------------------------------------------

  @doc "Revalidate a form against a fresh parameter map."
  @spec change(Form.t(), map(), Keyword.t()) :: Form.t()
  def change(form, params, opts \\ []), do: Form.validate(form, params, opts)

  @doc "Add a nested form at `path`."
  @spec add_nested(Form.t(), String.t(), Keyword.t()) :: Form.t()
  def add_nested(form, path, opts \\ []), do: Form.add_form(form, path, opts)

  @doc "Remove the nested form at `path`."
  @spec remove_nested(Form.t(), String.t()) :: Form.t()
  def remove_nested(form, path), do: Form.remove_form(form, path)

  @doc """
  Reorder the nested list at `path`, given the new ordering as a list of the
  current zero-based indices.
  """
  @spec reorder(Form.t(), String.t(), [non_neg_integer()]) :: Form.t()
  def reorder(form, path, order) do
    {parent_path, list_key} = split_list_path(form, path)

    Form.update_form(form, parent_path, fn parent ->
      parent
      |> Form.sort_forms([list_key], order)
      |> Form.touch(list_key)
    end)
  end

  @doc """
  Move the single nested form at `path` one slot earlier (`:up`) or later
  (`:down`). A no-op at either boundary of the list.
  """
  @spec move(Form.t(), String.t(), :up | :down) :: Form.t()
  def move(form, path, direction) when direction in [:up, :down] do
    {parent_path, list_key, index} = split_item_path(form, path)
    instruction = if direction == :up, do: :decrement, else: :increment

    Form.update_form(form, parent_path, fn parent ->
      parent
      |> Form.sort_forms([list_key, index], instruction)
      |> Form.touch(list_key)
    end)
  end

  defp split_list_path(form, path) do
    full_path = Form.parse_path!(form, path)
    {parent_path, [list_key]} = Enum.split(full_path, -1)
    {parent_path, list_key}
  end

  defp split_item_path(form, path) do
    full_path = Form.parse_path!(form, path)
    {parent_path, [list_key, index]} = Enum.split(full_path, -2)
    {parent_path, list_key, index}
  end

  # ---------------------------------------------------------------------
  # Inspecting forms
  # ---------------------------------------------------------------------

  @doc "The parameter map that would be sent to the underlying action."
  @spec submitted_params(Form.t()) :: map()
  def submitted_params(form), do: Form.params(form)

  @doc "The hidden inputs required to render the form at `path`."
  @spec hidden_inputs(Form.t(), String.t()) :: %{String.t() => String.t()}
  def hidden_inputs(form, path) do
    form
    |> fetch_form!(path)
    |> hidden_input_map()
  end

  @doc "The user-facing errors of the whole form tree."
  @spec error_map(Form.t()) :: %{String.t() => [[String.t()]]}
  def error_map(form) do
    form
    |> flatten_forms()
    |> Enum.reduce(%{}, fn nested, acc ->
      case own_errors(nested) do
        [] -> acc
        errors -> Map.put(acc, nested.name, errors)
      end
    end)
  end

  @doc "The untranslated errors of the form at `path`."
  @spec raw_error_list(Form.t(), String.t()) :: [{atom(), String.t(), Keyword.t()}]
  def raw_error_list(form, path) do
    form
    |> Form.errors(for_path: path, format: :raw)
    |> Enum.map(fn {field, {message, vars}} -> {field, message, vars} end)
    |> Enum.sort_by(fn {field, message, _vars} -> {to_string(field), message} end)
  end

  @doc "A deterministic, plain-data snapshot of the whole form tree."
  @spec serialize(Form.t()) :: map()
  def serialize(form) do
    %{
      "name" => form.name,
      "id" => form.id,
      "type" => to_string(form.type),
      "resource" => inspect(form.resource),
      "valid" => !!form.valid?,
      "hidden" => Map.delete(hidden_input_map(form), "_touched"),
      "values" => values_map(form),
      "errors" => own_errors(form),
      "nested" => nested_map(form)
    }
  end

  # ---------------------------------------------------------------------
  # Submitting forms
  # ---------------------------------------------------------------------

  @doc """
  Submit the form and persist the whole graph. `params` may be a fresh
  parameter map to validate into the form before submitting, or `nil` to
  submit what the form already holds.
  """
  @spec save(Form.t(), map() | nil) :: {:ok, Order.t()} | {:error, Form.t()}
  def save(form, params) do
    case Form.submit(form, params: params) do
      {:ok, order} -> {:ok, load_full_order!(order)}
      {:error, new_form} -> {:error, new_form}
    end
  end

  defp load_full_order!(order) do
    modifiers_query = Ash.Query.sort(Modifier, :position)

    line_items_query =
      LineItem
      |> Ash.Query.sort(:position)
      |> Ash.Query.load(modifiers: modifiers_query)

    Ash.load!(order, [:customer, line_items: line_items_query])
  end

  # ---------------------------------------------------------------------
  # Shared helpers
  # ---------------------------------------------------------------------

  defp fetch_form!(form, path) do
    case Form.get_form(form, path) do
      nil -> raise ArgumentError, "no form found at path #{inspect(path)}"
      target -> target
    end
  end

  defp hidden_input_map(target) do
    target
    |> Form.hidden_fields()
    |> Map.new(fn {key, value} -> {to_string(key), to_string(value)} end)
  end

  defp own_errors(form) do
    form
    |> Form.errors(format: :simple)
    |> Enum.map(fn {field, message} -> [to_string(field), message] end)
    |> Enum.sort()
  end

  defp values_map(form) do
    @value_fields
    |> Map.get(form.resource, [])
    |> Map.new(fn field ->
      {to_string(field), stringify(Form.value(form, field))}
    end)
  end

  defp stringify(nil), do: nil
  defp stringify(value), do: to_string(value)

  defp nested_map(form) do
    Map.new(form.forms, fn {key, value} -> {to_string(key), serialize_nested(value)} end)
  end

  defp serialize_nested(nil), do: nil
  defp serialize_nested(forms) when is_list(forms), do: Enum.map(forms, &serialize/1)
  defp serialize_nested(%Form{} = nested), do: serialize(nested)

  defp flatten_forms(form) do
    [
      form
      | form.forms
        |> Map.values()
        |> Enum.flat_map(&flatten_nested/1)
    ]
  end

  defp flatten_nested(nil), do: []
  defp flatten_nested(forms) when is_list(forms), do: Enum.flat_map(forms, &flatten_forms/1)
  defp flatten_nested(%Form{} = nested), do: flatten_forms(nested)
end
