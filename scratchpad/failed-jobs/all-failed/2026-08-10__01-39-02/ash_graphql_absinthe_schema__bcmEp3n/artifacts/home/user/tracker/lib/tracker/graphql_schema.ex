defmodule Tracker.GraphqlSchema.ValidateRelayIds do
  @behaviour Absinthe.Middleware

  def call(resolution, _opts) do
    case validate_args(resolution.definition.schema_node.identifier, resolution.arguments) do
      :ok ->
        resolution

      {:error, code} ->
        error = %{
          message: "invalid primary key provided",
          short_message: "invalid primary key provided",
          code: code,
          fields: []
        }

        if resolution.definition.parent_type.name == "RootMutationType" do
          Absinthe.Resolution.put_result(resolution, {:ok, %{result: nil, errors: [error]}})
        else
          Absinthe.Resolution.put_result(resolution, {:error, error})
        end
    end
  end

  defp validate_args(:ticket, %{id: id}), do: validate_global_id(id, :ticket)
  defp validate_args(:ticket_or_fail, %{id: id}), do: validate_global_id(id, :ticket)
  defp validate_args(:project, %{id: id}), do: validate_global_id(id, :project)
  defp validate_args(:node, %{id: id}), do: validate_any_global_id(id)
  defp validate_args(:update_ticket, %{id: id} = args) do
    with :ok <- validate_global_id(id, :ticket) do
      input = Map.get(args, :input) || %{}
      validate_global_id(Map.get(input, :assignee_id), :user)
    end
  end
  defp validate_args(:destroy_ticket, %{id: id}), do: validate_global_id(id, :ticket)
  defp validate_args(:archive_project, %{id: id}), do: validate_global_id(id, :project)
  defp validate_args(:create_ticket, args) do
    input = Map.get(args, :input) || %{}
    with :ok <- validate_global_id(Map.get(input, :project_id), :project) do
      validate_global_id(Map.get(input, :assignee_id), :user)
    end
  end
  defp validate_args(_, _), do: :ok

  defp validate_global_id(nil, _expected_type), do: :ok
  defp validate_global_id(value, expected_type) when is_binary(value) do
    case AshGraphql.Resource.decode_relay_id(value) do
      {:ok, %{type: ^expected_type, id: uuid}} ->
        if String.match?(uuid, ~r/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i) do
          :ok
        else
          {:error, "invalid_primary_key"}
        end
      _ ->
        {:error, "invalid_primary_key"}
    end
  end
  defp validate_global_id(_, _expected_type), do: {:error, "invalid_primary_key"}

  defp validate_any_global_id(value) when is_binary(value) do
    case AshGraphql.Resource.decode_relay_id(value) do
      {:ok, %{type: type, id: uuid}} when type in [:ticket, :project] ->
        if String.match?(uuid, ~r/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i) do
          :ok
        else
          {:error, "invalid_primary_key"}
        end
      _ ->
        {:error, "invalid_primary_key"}
    end
  end
  defp validate_any_global_id(_), do: {:error, "invalid_primary_key"}
end

defimpl AshGraphql.Error, for: Ash.Error.Unknown do
  def to_error(error) do
    msg =
      case error.errors do
        [first | _] -> Exception.message(first)
        _ -> "unknown error"
      end

    %{
      message: msg,
      short_message: msg,
      code: "unknown_error",
      fields: [],
      vars: %{}
    }
  end
end

defimpl AshGraphql.Error, for: RuntimeError do
  def to_error(error) do
    %{
      message: error.message,
      short_message: error.message,
      code: "unknown_error",
      fields: [],
      vars: %{}
    }
  end
end

defimpl AshGraphql.Error, for: Tracker.Delivery.Errors.SprintFrozen do
  def to_error(error) do
    %{
      message: "sprint #{error.project_slug} is already frozen",
      short_message: "sprint frozen",
      code: "sprint_frozen",
      fields: ["reason"],
      vars: %{project_slug: error.project_slug}
    }
  end
end

defmodule Tracker.GraphqlSchema do
  use Absinthe.Schema

  use AshGraphql,
    domains: [Tracker.Delivery],
    relay_ids?: true,
    action_middleware: [Tracker.GraphqlSchema.ValidateRelayIds]

  # Custom types
  object :api_info do
    field :name, non_null(:string)
    field :ticket_count, non_null(:integer)
  end

  query do
    field :api_info, non_null(:api_info) do
      resolve fn _, %{context: context} ->
        # Count the tickets
        case Ash.read(Tracker.Delivery.Ticket, actor: Map.get(context, :actor), authorize?: false) do
          {:ok, tickets} ->
            {:ok, %{name: "tracker", ticket_count: Enum.count(tickets)}}
          _ ->
            {:ok, %{name: "tracker", ticket_count: 0}}
        end
      end
    end

    field :ticket_by_reference, :ticket do
      arg :reference, non_null(:string)

      resolve fn %{reference: reference}, resolution ->
        require Ash.Query
        context = resolution.context
        actor = Map.get(context, :actor)
        domain = Tracker.Delivery
        resource = Tracker.Delivery.Ticket

        # Build initial query
        query =
          resource
          |> Ash.Query.new()
          |> Ash.Query.for_read(:read, %{}, actor: actor)
          |> Ash.Query.filter(internal_reference: reference)
          |> AshGraphql.Graphql.Resolver.select_fields(resource, resolution, :ticket)
          |> AshGraphql.Graphql.Resolver.load_fields(
            [
              domain: domain,
              tenant: Map.get(context, :tenant),
              authorize?: AshGraphql.Domain.Info.authorize?(domain),
              tracer: AshGraphql.Domain.Info.tracer(domain),
              actor: actor
            ],
            resource,
            resolution,
            resolution.path,
            context,
            :ticket
          )

        # Execute query
        case Ash.read_one(query, actor: actor, authorize?: AshGraphql.Domain.Info.authorize?(domain)) do
          {:ok, ticket} ->
            {:ok, ticket} # This will be %Ticket{} or nil
          {:error, error} ->
            {:error, error}
        end
      end
    end
  end

  mutation do
    # Derived mutations will be injected here
  end
end
