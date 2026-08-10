defmodule Kbapi.MixProject do
  use Mix.Project

  def project do
    [
      app: :kbapi,
      version: "0.1.0",
      elixir: "~> 1.18",
      start_permanent: false,
      deps: deps()
    ]
  end

  def application do
    [extra_applications: [:logger], mod: {Kbapi.Application, []}]
  end

  defp deps do
    [
      {:ash, "~> 3.31"},
      {:ash_json_api, "~> 1.7"},
      {:simple_sat, "~> 0.1"},
      {:jason, "~> 1.4"},
      {:plug, "~> 1.16"},
      {:open_api_spex, "~> 3.21"}
    ]
  end
end
