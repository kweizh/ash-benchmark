{:ok, _} = Application.ensure_all_started(:orchestra)
{:ok, ar} = Reactor.Info.to_struct(Orchestra.Rollout.ApprovalReactor)
for step <- ar.steps do
  impl = if is_tuple(step.impl), do: elem(step.impl, 0), else: step.impl
  if impl == Reactor.Step.Switch do
    opts = elem(step.impl, 1)
    IO.inspect(Keyword.keys(opts), label: "switch keys")
    IO.inspect(opts[:on], label: "on")
    matches = opts[:matches]
    IO.inspect(length(matches), label: "matches count")
    [m0 | _] = matches
    IO.inspect(elem(m0, 0), label: "match0 predicate")
    IO.inspect(Enum.map(elem(m0, 1), & &1.name), label: "match0 step names")
    d = opts[:default]
    IO.inspect(Enum.map(d.steps, & &1.name), label: "default step names")
  end
end
