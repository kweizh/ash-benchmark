defmodule Kbapi.Api.Endpoint do
  @moduledoc false
  use Plug.Builder
  require Ash.Query

  alias Kbapi.Knowledge.Author

  @json_api "application/vnd.api+json"

  plug Plug.Parsers,
    parsers: [:json],
    pass: ["application/vnd.api+json"],
    json_decoder: Jason

  plug :check_required_type
  plug :resolve_actor
  plug :dispatch

  defp check_required_type(conn, _opts) do
    if conn.method in ["PATCH"] and json_api_content_type?(conn) do
      case conn.body_params do
        %{"data" => data} when is_map(data) and not is_map_key(data, "type") ->
          conn
          |> put_resp_content_type(@json_api)
          |> send_resp(400, missing_type_error())
          |> halt()

        _ ->
          conn
      end
    else
      conn
    end
  end

  defp json_api_content_type?(conn) do
    case get_req_header(conn, "content-type") do
      [content_type | _] ->
        String.starts_with?(content_type, "application/vnd.api+json")

      [] ->
        false
    end
  end

  defp missing_type_error do
    Jason.encode!(%{
      errors: [
        %{
          id: Ash.UUID.generate(),
          status: "400",
          code: "missing_type",
          title: "Invalid resource object",
          detail: "The resource object MUST contain at least a type member.",
          source: %{pointer: "/data"},
          meta: %{}
        }
      ],
      jsonapi: %{version: "1.0"}
    })
  end

  defp resolve_actor(conn, _opts) do
    case get_req_header(conn, "x-actor-handle") do
      [handle | _] ->
        query = Ash.Query.filter(Author, handle == ^handle)

        case Ash.read_one(query, authorize?: false) do
          {:ok, nil} ->
            conn
            |> put_resp_content_type(@json_api)
            |> send_resp(401, unknown_actor_error(handle))
            |> halt()

          {:ok, author} ->
            Ash.PlugHelpers.set_actor(conn, author)

          {:error, _} ->
            conn
            |> put_resp_content_type(@json_api)
            |> send_resp(401, unknown_actor_error(handle))
            |> halt()
        end

      [] ->
        conn
    end
  end

  defp unknown_actor_error(handle) do
    Jason.encode!(%{
      errors: [
        %{
          code: "unknown_actor",
          status: "401",
          title: "Unauthorized",
          detail: "unknown actor handle #{handle}"
        }
      ]
    })
  end

  defp dispatch(%{halted: true} = conn, _opts), do: conn

  defp dispatch(conn, _opts) do
    case conn.path_info do
      ["api" | rest] ->
        conn = %{conn | path_info: rest, script_name: conn.script_name ++ ["api"]}
        Kbapi.Api.Router.call(conn, Kbapi.Api.Router.init([]))

      _ ->
        conn
        |> put_resp_content_type(@json_api)
        |> send_resp(404, not_found_error())
        |> halt()
    end
  end

  defp not_found_error do
    Jason.encode!(%{
      errors: [
        %{
          code: "not_found",
          status: "404",
          title: "NotFound",
          detail: "no route found"
        }
      ]
    })
  end
end
