defmodule Lifecycle.Records.ArchivalEvent do
  @moduledoc """
  An append-only audit row describing that some record was archived.

  Rows are written through the `:record` action.
  """
  use Ash.Resource,
    otp_app: :lifecycle,
    domain: Lifecycle.Records,
    data_layer: Ash.DataLayer.Ets

  ets do
    private? true
  end

  attributes do
    uuid_primary_key :id
    attribute :subject_id, :uuid, allow_nil?: false, public?: true
    attribute :subject_type, :string, allow_nil?: false, public?: true
    attribute :reason_code, :string, allow_nil?: false, public?: true
    attribute :occurred_at, :utc_datetime_usec, allow_nil?: false, public?: true
  end

  actions do
    defaults [:read, :destroy]

    create :record do
      accept [:subject_id, :subject_type, :reason_code, :occurred_at]
    end
  end
end
