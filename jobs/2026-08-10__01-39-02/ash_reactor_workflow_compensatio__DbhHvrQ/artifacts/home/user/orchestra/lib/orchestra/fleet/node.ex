defmodule Orchestra.Fleet.Node do
  use Ash.Resource,
    domain: Orchestra.Fleet,
    data_layer: Ash.DataLayer.Ets

  attributes do
    uuid_primary_key :id
    attribute :name, :string, allow_nil?: false
    attribute :region, :atom, allow_nil?: false, constraints: [one_of: [:us_east, :eu_west, :ap_south]]
    attribute :slots_total, :integer, allow_nil?: false
    attribute :slots_used, :integer, default: 0, allow_nil?: false
    attribute :state, :atom, default: :idle, allow_nil?: false, constraints: [one_of: [:idle, :reserved, :live]]
    attribute :deploy_failures_remaining, :integer, default: 0, allow_nil?: false
  end

  actions do
    defaults [:read, :destroy]

    create :create do
      accept [:name, :region, :slots_total, :deploy_failures_remaining]
      primary? true
    end

    update :update do
      accept [:slots_used, :state, :deploy_failures_remaining]
      primary? true
    end

    read :get_by_name do
      argument :name, :string, allow_nil?: false
      filter expr(name == ^arg(:name))
      get? true
    end

    update :undo_reserve do
      require_atomic? false
      argument :changeset, :term

      change fn changeset, _context ->
        original_changeset = Ash.Changeset.get_argument(changeset, :changeset)
        if original_changeset do
          prev_slots_used = original_changeset.data.slots_used
          prev_state = if prev_slots_used == 0, do: :idle, else: original_changeset.data.state

          # Record reserve_undo trace entry
          Orchestra.Rollout.Trace.record(:reserve_undo, original_changeset.data.name)

          changeset
          |> Ash.Changeset.force_change_attribute(:slots_used, prev_slots_used)
          |> Ash.Changeset.force_change_attribute(:state, prev_state)
        else
          changeset
        end
      end
    end
  end
end
