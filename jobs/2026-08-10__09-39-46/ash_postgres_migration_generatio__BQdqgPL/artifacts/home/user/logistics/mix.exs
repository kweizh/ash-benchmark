defmodule Logistics.MixProject do
  use Mix.Project

  def project do
    [
      app: :logistics,
      version: "0.1.0",
      elixir: "~> 1.18",
      start_permanent: false,
      deps: deps()
    ]
  end

  def application do
    [
      extra_applications: [:logger],
      mod: {Logistics.Application, []}
    ]
  end

  defp deps do
    [
      {:ash, "~> 3.31"},
      {:ash_postgres, "~> 2.11"}
    ]
  end
end
