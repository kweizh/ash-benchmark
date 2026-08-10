defmodule Orchestra.Rollout.ApprovalReactor do
  use Ash.Reactor

  input :rollout_id
  input :total_slots
  input :board_threshold

  middlewares do
    middleware Orchestra.Rollout.Middleware
  end

  step :prepare_switch_input do
    argument :total_slots, input(:total_slots)
    argument :board_threshold, input(:board_threshold)

    run fn %{total_slots: total, board_threshold: threshold}, _ ->
      {:ok, %{total_slots: total, board_threshold: threshold}}
    end
  end

  switch :choose_level do
    on result(:prepare_switch_input)

    matches? fn %{total_slots: total, board_threshold: threshold} -> total >= threshold end do
      create :create_board_approval, Orchestra.Fleet.Approval, :create do
        inputs %{
          rollout_id: input(:rollout_id),
          level: value(:board),
          slots: input(:total_slots),
          status: value(:granted)
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
          slots: input(:total_slots),
          status: value(:granted)
        }
        undo :always
        undo_action :revoke
      end

      return :create_auto_approval
    end
  end

  return :choose_level
end
