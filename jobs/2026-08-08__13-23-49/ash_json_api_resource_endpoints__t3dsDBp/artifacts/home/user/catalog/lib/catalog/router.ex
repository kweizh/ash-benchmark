defmodule Catalog.Router do
  use Plug.Router
  require Ash.Query

  plug Plug.Parsers,
    parsers: [:urlencoded, :multipart, :json, AshJsonApi.Plug.Parser],
    pass: ["*/*"],
    json_decoder: Jason

  plug :set_actor

  plug :match
  plug :dispatch

  defp set_actor(conn, _opts) do
    role =
      case Plug.Conn.get_req_header(conn, "x-actor-role") do
        ["curator" | _] -> :curator
        _ -> :user
      end

    Ash.PlugHelpers.set_actor(conn, %{role: role})
  end

  get "/api/json/reports/shelf_summary" do
    conn = fetch_query_params(conn)
    case conn.query_params["shelf"] do
      nil ->
        error_payload = %{
          "errors" => [
            %{
              "id" => Ash.UUID.generate(),
              "status" => "400",
              "code" => "required",
              "title" => "Required Parameter Missing",
              "detail" => "The query parameter 'shelf' is required.",
              "source" => %{"parameter" => "shelf"}
            }
          ]
        }
        conn
        |> put_resp_content_type("application/vnd.api+json")
        |> send_resp(400, Jason.encode!(error_payload))

      shelf ->
        book_query =
          Catalog.Library.Book
          |> Ash.Query.filter(shelf == ^shelf)

        books = Ash.read!(book_query, authorize?: false)
        book_ids = Enum.map(books, & &1.id)

        review_query =
          Catalog.Library.Review
          |> Ash.Query.filter(book_id in ^book_ids)

        reviews = Ash.read!(review_query, authorize?: false)

        book_count = length(books)
        review_count = length(reviews)
        total_price_cents = Enum.sum(Enum.map(books, & &1.price_cents))

        response = %{
          "result" => %{
            "shelf" => shelf,
            "book_count" => book_count,
            "review_count" => review_count,
            "total_price_cents" => total_price_cents
          }
        }

        conn
        |> put_resp_content_type("application/vnd.api+json")
        |> send_resp(200, Jason.encode!(response))
    end
  end

  forward "/api/json", to: Catalog.JsonApiRouter
end
