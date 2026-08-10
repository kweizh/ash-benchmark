defmodule Tracker.MixProject do
  use Mix.Project

  def project do
    [
      app: :tracker,
      version: "0.1.0",
      elixir: "~> 1.18",
      start_permanent: Mix.env() == :prod,
      consolidate_protocols: Mix.env() != :dev,
      deps: deps()
    ]
  end

  def application do
    [
      extra_applications: [:logger],
      mod: {Tracker.Application, []}
    ]
  end

  defp deps do
    [
      {:ash, "~> 3.31"},
      {:ash_graphql, "~> 1.10"},
      {:simple_sat, "~> 0.1"}
    ]
  end
end
