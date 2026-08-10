defmodule Tracker.GraphqlSchema do
  @moduledoc false
  use Absinthe.Schema

  use AshGraphql,
    domains: [Tracker.Delivery],
    relay_ids?: true

  require Ash.Query

  query do
    field :api_info, non_null(:api_info) do
      description "Static metadata about this API"

      resolve fn _args, _resolution ->
        {:ok,
         %{
           name: "tracker",
           ticket_count: Ash.count!(Tracker.Delivery.Ticket)
         }}
      end
    end

    field :ticket_by_reference, :ticket do
      description "Fetch a ticket by its internal reference"

      arg :reference, non_null(:string)

      resolve fn %{reference: reference}, resolution ->
        Tracker.Delivery.Ticket
        |> Ash.Query.filter(internal_reference == ^reference)
        |> AshGraphql.load_fields_on_query(resolution)
        |> Ash.read_one()
        |> AshGraphql.handle_errors(Tracker.Delivery.Ticket, resolution)
      end
    end
  end

  mutation do
  end

  object :api_info do
    field :name, non_null(:string)
    field :ticket_count, non_null(:integer)
  end
end
