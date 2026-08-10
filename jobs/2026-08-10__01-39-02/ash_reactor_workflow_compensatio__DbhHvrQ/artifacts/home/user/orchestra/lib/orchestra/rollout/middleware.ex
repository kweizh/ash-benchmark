defmodule Orchestra.Rollout.Middleware do
  use Reactor.Middleware

  @impl true
  def init(context) do
    Orchestra.Rollout.Trace.record(:reactor_init, "reactor")
    {:ok, context}
  end

  @impl true
  def complete(result, _context) do
    Orchestra.Rollout.Trace.record(:reactor_complete, "reactor")
    {:ok, result}
  end

  @impl true
  def error(_error_or_errors, _context) do
    Orchestra.Rollout.Trace.record(:reactor_error, "reactor")
    :ok
  end

  @impl true
  def event(step_event, step, _context) do
    event_tag =
      case step_event do
        tuple when is_tuple(tuple) -> elem(tuple, 0)
        atom when is_atom(atom) -> atom
      end

    label = inspect(step.name)
    Orchestra.Rollout.Trace.record(event_tag, label)
    :ok
  end
end
