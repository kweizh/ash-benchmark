defmodule Catalog.ActorPlug do
  @moduledoc """
  A Plug that reads the `x-actor-role` header and sets the actor in the conn's private :ash map.

  If the header value is "curator", the actor is `%{role: :curator}`.
  Otherwise, the actor is `%{role: :anonymous}`.
  If the header is missing, the actor is `%{role: :anonymous}`.
  """

  @behaviour Plug

  import Plug.Conn
  import Ash.PlugHelpers

  @impl true
  def init(opts), do: opts

  @impl true
  def call(conn, _opts) do
    role =
      case get_req_header(conn, "x-actor-role") do
        ["curator"] -> :curator
        _ -> :anonymous
      end

    conn
    |> set_actor(%{role: role})
  end
end
