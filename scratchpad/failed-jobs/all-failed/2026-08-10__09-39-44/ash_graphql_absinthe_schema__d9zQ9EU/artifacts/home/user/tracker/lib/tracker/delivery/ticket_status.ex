defmodule Tracker.Delivery.TicketStatus do
  @moduledoc false
  use Ash.Type.Enum, values: [:open, :in_progress, :blocked, :done]
end
