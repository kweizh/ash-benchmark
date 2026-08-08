defmodule Forum.Content.Reaction do
  @moduledoc """
  A reaction on a forum comment. Has no children.
  """
  use Ash.Resource,
    otp_app: :forum,
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
      allow_nil? false
      attribute_writable? true
      public? true
    end
  end

  actions do
    create :create do
      primary? true
      accept [:emoji, :comment_id]
    end

    read :read do
      primary? true
      prepare {Forum.Archive.Preparations.ArchiveScope, scope: :live}
    end

    read :archived do
      prepare {Forum.Archive.Preparations.ArchiveScope, scope: :archived}
    end

    read :with_archived do
      prepare {Forum.Archive.Preparations.ArchiveScope, scope: :all}
    end

    destroy :archive do
      soft? true
      require_atomic? false
      change {Forum.Archive.Changes.CascadeArchive, relationship: nil}
    end

    update :restore do
      require_atomic? false
      accept []
      change {Forum.Archive.Changes.CascadeRestore, relationship: nil}
    end

    destroy :purge do
      require_atomic? false

      validate fn changeset, _context ->
        if changeset.context[:cascade_purge] do
          :ok
        else
          if is_nil(changeset.data.archived_at) do
            {:error,
             Ash.Error.Changes.InvalidChanges.exception(
               fields: [:archived_at],
               message: "must be archived before it can be purged"
             )}
          else
            :ok
          end
        end
      end

      change {Forum.Archive.Changes.CascadePurge, relationship: nil}
    end
  end

  policies do
    policy action(:archived) do
      access_type :strict
      authorize_if actor_attribute_equals(:role, :admin)
    end

    policy always() do
      authorize_if always()
    end
  end
end
