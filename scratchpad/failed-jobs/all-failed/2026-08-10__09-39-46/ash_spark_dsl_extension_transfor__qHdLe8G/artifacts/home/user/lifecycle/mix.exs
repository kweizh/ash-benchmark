defmodule Lifecycle.MixProject do
  use Mix.Project

  def project do
    [
      app: :lifecycle,
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
      {:spark, "== 2.7.2"},
      {:jason, "== 1.4.5"}
    ]
  end
end
