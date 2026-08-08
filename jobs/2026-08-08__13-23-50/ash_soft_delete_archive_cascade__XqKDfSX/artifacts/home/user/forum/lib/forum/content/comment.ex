defmodule Forum.Content.Comment do
  @moduledoc """
  A comment on a forum post. Owns reactions.
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

    attribute :body, :string do
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
    belongs_to :post, Forum.Content.Post do
      allow_nil? false
      attribute_writable? true
      public? true
    end

    has_many :reactions, Forum.Content.Reaction
  end

  aggregates do
    count :reaction_count, :reactions do
      public? true
    end
  end

  actions do
    create :create do
      primary? true
      accept [:body, :post_id]
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
      change {Forum.Archive.Changes.CascadeArchive, relationship: :reactions}
    end

    update :restore do
      require_atomic? false
      accept []
      change {Forum.Archive.Changes.CascadeRestore, relationship: :reactions}
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

      change {Forum.Archive.Changes.CascadePurge, relationship: :reactions}
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
