defmodule Forum.Content.Post do
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

    attribute :title, :string do
      public? true
      allow_nil? false
    end

    attribute :archived_at, :utc_datetime_usec do
      public? true
    end

    attribute :archive_batch_id, :uuid do
      public? true
    end
  end

  relationships do
    has_many :comments, Forum.Content.Comment do
      destination_attribute :post_id
    end
  end

  aggregates do
    count :comment_count, :comments do
      public? true
    end
  end

  actions do
    create :create do
      primary? true
      accept [:title]
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

      change fn changeset, _context ->
        Ash.Changeset.before_action(changeset, fn changeset ->
          parent_id = changeset.data.id

          comments =
            Forum.Content.Comment
            |> Ash.Query.for_read(:with_archived, %{})
            |> Ash.Query.filter(post_id == ^parent_id)
            |> Ash.read!(authorize?: false)

          for comment <- comments do
            Ash.destroy!(comment, action: :purge, authorize?: false)
          end

          changeset
         end)
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
