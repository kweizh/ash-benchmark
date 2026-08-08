defmodule Forum.MixProject do
  use Mix.Project

  def project do
    [
      app: :forum,
      version: "0.1.0",
      elixir: "~> 1.18",
      start_permanent: Mix.env() == :prod,
      deps: deps()
    ]
  end

  def application do
    [extra_applications: [:logger]]
  end

  defp deps do
    [
      {:ash, "== 3.31.0"},
      {:simple_sat, "== 0.1.4"}
    ]
  end
end
