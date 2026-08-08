defmodule Outbox.MixProject do
  use Mix.Project

  def project do
    [
      app: :outbox,
      version: "0.1.0",
      elixir: "~> 1.18",
      start_permanent: false,
      deps: deps()
    ]
  end

  def application do
    [
      extra_applications: [:logger],
      mod: {Outbox.Application, []}
    ]
  end

  defp deps do
    [
      {:ash, "~> 3.31"}
    ]
  end
end
