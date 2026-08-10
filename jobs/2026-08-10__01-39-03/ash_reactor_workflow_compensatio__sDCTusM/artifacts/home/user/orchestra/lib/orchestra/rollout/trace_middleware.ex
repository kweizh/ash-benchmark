defmodule Orchestra.Rollout.TraceMiddleware do
  @moduledoc """
  A `Reactor.Middleware` which records reactor lifecycle and step events onto
  `Orchestra.Rollout.Trace`.
  """
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
  def error(_errors, _context) do
    Trace.record({:reactor_error, "reactor"})
    :ok
  end

  @impl true
  def event(event, step, _context) do
    tag = if is_tuple(event), do: elem(event, 0), else: event
    Trace.record({tag, inspect(step.name)})
    :ok
  end
end
