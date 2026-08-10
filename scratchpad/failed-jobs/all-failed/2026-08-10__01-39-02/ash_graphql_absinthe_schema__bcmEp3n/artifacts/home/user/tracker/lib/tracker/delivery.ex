defmodule Tracker.Delivery.ErrorHandler do
  def handle_error(error_map, _context) do
    # 1. Convert fields to strings, and map Ash attribute names to GraphQL field names
    fields =
      case error_map[:fields] do
        list when is_list(list) ->
          Enum.map(list, fn
            :estimate_points -> "points"
            other ->
              other
              |> to_string()
              |> Absinthe.Utils.camelize(lower: true)
          end)

        _ ->
          []
      end

    error_map = %{error_map | fields: fields}

    # 2. If code is "not_found", ensure fields is ["id"]
    error_map =
      if error_map[:code] == "not_found" do
        %{error_map | fields: ["id"]}
      else
        error_map
      end

    # 3. If code is "forbidden", make sure code, message and shortMessage are all "forbidden" and fields is []
    error_map =
      if error_map[:code] == "forbidden" do
        %{error_map | message: "forbidden", short_message: "forbidden", fields: []}
      else
        error_map
      end

    error_map
  end
end

defmodule Tracker.Delivery do
  @moduledoc false
  use Ash.Domain,
    otp_app: :tracker,
    extensions: [AshGraphql.Domain]

  resources do
    resource Tracker.Delivery.User
    resource Tracker.Delivery.Project
    resource Tracker.Delivery.Ticket
    resource Tracker.Delivery.Label
    resource Tracker.Delivery.TicketLabel
  end

  graphql do
    show_raised_errors? true
    error_handler {Tracker.Delivery.ErrorHandler, :handle_error, []}
  end
end
