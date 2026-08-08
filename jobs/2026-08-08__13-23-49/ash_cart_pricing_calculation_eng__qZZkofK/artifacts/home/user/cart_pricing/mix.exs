defmodule CartPricing.MixProject do
  use Mix.Project

  def project do
    [
      app: :cart_pricing,
      version: "0.1.0",
      elixir: "~> 1.18",
      elixirc_paths: elixirc_paths(Mix.env()),
      start_permanent: Mix.env() == :prod,
      deps: deps()
    ]
  end

  def application do
    [
      extra_applications: [:logger]
    ]
  end

  defp elixirc_paths(:test), do: ["lib"]
  defp elixirc_paths(_), do: ["lib"]

  defp deps do
    [
      {:ash, "== 3.31.0"},
      {:jason, "~> 1.4"}
    ]
  end
end
