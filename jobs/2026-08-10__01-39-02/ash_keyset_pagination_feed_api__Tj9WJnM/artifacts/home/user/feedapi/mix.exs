defmodule Feedapi.MixProject do
  use Mix.Project

  def project do
    [
      app: :feedapi,
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
      {:jason, "~> 1.4"}
    ]
  end
end
