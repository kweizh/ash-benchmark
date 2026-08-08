defmodule Forum.Content.Reaction do
  @moduledoc """
  A reaction (emoji) on a comment.
  """

  use Ash.Resource,
    domain: Forum.Content,
    data_layer: Ash.DataLayer.Ets,
    authorizers: [Ash.Policy.Authorizer],
    primary_read_warning?: false

  ets do
    private? true
  end

  attributes do
    uuid_primary_key :id

    attribute :emoji, :string do
      public? true
      allow_nil? false
    end

    attribute :comment_id, :uuid do
      public? true
      allow_nil? false
    end

    attribute :archived_at, :utc_datetime_usec do
      public? true
      allow_nil? true
    end

    attribute :archive_batch_id, :uuid do
      public? true
      allow_nil? true
    end
  end

  relationships do
    belongs_to :comment, Forum.Content.Comment do
      public? true
      attribute_type :uuid
      allow_nil? false
    end
  end

  policies do
    policy action(:archived) do
      authorize_if actor_attribute_equals(:role, :admin)
    end

    policy always() do
      authorize_if always()
    end
  end

  actions do
    default_accept :*

    read :read do
      primary? true
      prepare Forum.Archive.Preparations.ArchiveScope
    end

    read :archived do
      prepare Forum.Archive.Preparations.ArchiveScope
    end

    read :with_archived do
      prepare Forum.Archive.Preparations.ArchiveScope
    end

    create :create do
      accept [:emoji, :comment_id]
    end

    update :restore do
      require_atomic? false
      change Forum.Archive.Changes.CascadeRestore
    end

    destroy :archive do
      soft? true
      require_atomic? false
      change Forum.Archive.Changes.CascadeArchive
    end

    destroy :purge do
      soft? false
      require_atomic? false
      change {Forum.Archive.Changes.ValidateArchivedForPurge, []}
    end
  end
end
