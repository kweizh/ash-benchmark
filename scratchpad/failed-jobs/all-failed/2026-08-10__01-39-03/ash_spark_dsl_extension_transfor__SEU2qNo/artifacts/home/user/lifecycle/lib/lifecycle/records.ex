defmodule Lifecycle.Records do
  @moduledoc """
  The domain that groups the record resources of this application.
  """
  use Ash.Domain, otp_app: :lifecycle

  resources do
    resource Lifecycle.Records.ArchivalEvent
  end
end
