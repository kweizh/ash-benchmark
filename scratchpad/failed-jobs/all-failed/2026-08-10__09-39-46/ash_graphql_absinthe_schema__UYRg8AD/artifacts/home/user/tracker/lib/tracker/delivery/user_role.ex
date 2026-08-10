defmodule Tracker.Delivery.UserRole do
  @moduledoc false
  use Ash.Type.Enum, values: [:member, :admin]
end
