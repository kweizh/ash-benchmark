defmodule Forum.Content.Reaction do
  use Ash.Resource,
    domain: Forum.Content,
    data_layer: Ash.DataLayer.Ets,
    authorizers: [Ash.Policy.Authorizer],
    primary_read_warning?: false

  require Ash.Query

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
      writable? true
    end

    attribute :archived_at, :utc_datetime_usec do
      public? true
    end

    attribute :archive_batch_id, :uuid do
      public? true
    end
  end

  relationships do
    belongs_to :comment, Forum.Content.Comment do
      define_attribute? false
      source_attribute :comment_id
    end
  end

  actions do
    create :create do
      primary? true
      accept [:emoji, :comment_id]
    end

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

    destroy :archive do
      soft? true
      require_atomic? false
      change Forum.Archive.Changes.CascadeArchive
    end

    update :restore do
      require_atomic? false
      change Forum.Archive.Changes.CascadeRestore
    end

    destroy :purge do
      require_atomic? false

      validate fn changeset, _context ->
        if is_nil(changeset.data.archived_at) do
          {:error, Ash.Error.Changes.InvalidChanges.exception(
            fields: [:archived_at],
            message: "must be archived before it can be purged"
          )}
        else
          :ok
        end
      end
    end
  end

  policies do
    policy action(:archived) do
      access_type :strict
      authorize_if actor_attribute_equals(:role, :admin)
    end

    policy action([:create, :read, :with_archived, :archive, :restore, :purge]) do
      authorize_if always()
    end
  end
end
