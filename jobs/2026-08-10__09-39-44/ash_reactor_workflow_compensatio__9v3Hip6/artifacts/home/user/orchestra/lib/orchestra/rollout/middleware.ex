defmodule Orchestra.Rollout.Middleware do
  @moduledoc false

  use Reactor.Middleware

  alias Orchestra.Rollout.Trace

  @impl true
  def init(context) do
    Trace.record({:reactor_init, "reactor"})
    {:ok, context}
  end

  @impl true
  def complete(result, _context) do
    Trace.record({:reactor_complete, "reactor"})
    {:ok, result}
  end

  @impl true
  def error(_reason, _context) do
    Trace.record({:reactor_error, "reactor"})
    :ok
  end

  @impl true
  def event(event, step, _context) do
    tag =
      case event do
        tag when is_atom(tag) -> tag
        tuple -> elem(tuple, 0)
      end

    Trace.record({tag, inspect(step.name)})
    :ok
  end
end
