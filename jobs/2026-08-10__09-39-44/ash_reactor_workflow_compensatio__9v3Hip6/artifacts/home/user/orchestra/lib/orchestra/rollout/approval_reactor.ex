defmodule Orchestra.Rollout.ApprovalReactor do
  @moduledoc false

  use Ash.Reactor

  input :rollout_id
  input :total_slots
  input :board_threshold

  collect :threshold do
    argument :total_slots, input(:total_slots)
    argument :board_threshold, input(:board_threshold)
  end

  switch :approval do
    on result(:threshold)

    matches? fn %{total_slots: total_slots, board_threshold: board_threshold} ->
      total_slots >= board_threshold
    end do
      create :create_board_approval, Orchestra.Fleet.Approval, :create do
        inputs %{
          rollout_id: input(:rollout_id),
          level: value(:board),
          slots: input(:total_slots)
        }

        undo :always
        undo_action :revoke
      end

      return :create_board_approval
    end

    default do
      create :create_auto_approval, Orchestra.Fleet.Approval, :create do
        inputs %{
          rollout_id: input(:rollout_id),
          level: value(:auto),
          slots: input(:total_slots)
        }

        undo :always
        undo_action :revoke
      end

      return :create_auto_approval
    end
  end

  return :approval
end
