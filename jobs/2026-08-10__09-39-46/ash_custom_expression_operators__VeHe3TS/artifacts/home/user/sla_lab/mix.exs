defmodule SlaLab.MixProject do
  use Mix.Project

  def project do
    [
      app: :sla_lab,
      version: "0.1.0",
      elixir: "~> 1.18",
      start_permanent: false,
      deps: deps()
    ]
  end

  def application do
    [extra_applications: [:logger]]
  end

  defp deps do
    [
      {:ash, "== 3.31.0"},
      {:picosat_elixir, "== 0.2.3"}
    ]
  end
end
