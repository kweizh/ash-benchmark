defmodule Orchestra.Rollout.ApprovalReactor do
  @moduledoc """
  Independently runnable reactor which grants an approval for a rollout,
  choosing between `:auto` and `:board` approval levels based on the total
  slot count vs. the configured board threshold.
  """
  use Ash.Reactor

  alias Orchestra.Fleet.Approval

  ash do
    default_domain Orchestra.Fleet
  end

  input :rollout_id
  input :total_slots
  input :board_threshold

  step :needs_board do
    argument :total_slots, input(:total_slots)
    argument :threshold, input(:board_threshold)

    run fn %{total_slots: total_slots, threshold: threshold}, _context ->
      {:ok, total_slots >= threshold}
    end
  end

  switch :choose_level do
    on result(:needs_board)

    matches? & &1 do
      step :board_level do
        run fn _, _ -> {:ok, :board} end
      end

      return :board_level
    end

    default do
      step :auto_level do
        run fn _, _ -> {:ok, :auto} end
      end

      return :auto_level
    end
  end

  create :create_approval, Approval, :create do
    inputs %{
      rollout_id: input(:rollout_id),
      slots: input(:total_slots),
      level: result(:choose_level)
    }

    undo :always
    undo_action :revoke
  end

  return :create_approval
end
