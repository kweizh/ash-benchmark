FROM ubuntu:24.04

ARG POCHI_VERSION
ARG OTP_VERSION=27.3.4
ARG ELIXIR_VERSION=1.18.4

RUN apt-get update -y && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        curl wget ca-certificates git python3 python3-pip python3-pytest bash ripgrep \
        unzip build-essential libncurses6 libssl-dev && \
    ln -s /usr/bin/python3 /usr/bin/python && \
    curl -fsSL https://getpochi.com/install.sh | bash -s ${POCHI_VERSION} && \
    ln -s /root/.pochi/bin/pochi /usr/local/bin/pochi && \
    pip3 install --break-system-packages pytest-json-ctrf && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Pinned Erlang/OTP and Elixir builds from builds.hex.pm (arch aware, amd64 and arm64).
RUN mkdir -p /opt/otp && \
    curl -fsSL "https://builds.hex.pm/builds/otp/$(dpkg --print-architecture)/ubuntu-24.04/OTP-${OTP_VERSION}.tar.gz" \
      | tar -xz -C /opt/otp --strip-components=1 && \
    cd /opt/otp && \
    ./Install -minimal /opt/otp

RUN mkdir -p /opt/elixir && \
    curl -fsSL -o /tmp/elixir.zip "https://builds.hex.pm/builds/elixir/v${ELIXIR_VERSION}-otp-27.zip" && \
    unzip -q /tmp/elixir.zip -d /opt/elixir && \
    rm -f /tmp/elixir.zip

ENV PATH="/opt/otp/bin:/opt/elixir/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
ENV MIX_HOME=/opt/mix
ENV HEX_HOME=/opt/hex
ENV LANG=C.UTF-8

RUN mkdir -p /opt/mix /opt/hex && \
    mix local.hex --force && \
    mix local.rebar --force && \
    chmod -R a+rX /opt/mix /opt/hex

RUN mkdir -p /home/user && chmod 0755 /home/user

RUN mkdir -p /home/user/ledger/config /home/user/ledger/lib/ledger/billing /home/user/ledger/test

RUN cat > /home/user/ledger/mix.exs <<'EOF'
defmodule Ledger.MixProject do
  use Mix.Project

  def project do
    [
      app: :ledger,
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
      {:ash, "~> 3.31"},
      {:jason, "~> 1.4"}
    ]
  end
end
EOF

RUN cat > /home/user/ledger/mix.lock <<'EOF'
%{
  "ash": {:hex, :ash, "3.31.0", "9ccd7d5ff00a5329a33786063e4a3040681b61d736730cd7aa3f24e5843c1d4f", [:mix], [{:crux, ">= 0.1.2 and < 1.0.0-0", [hex: :crux, repo: "hexpm", optional: false]}, {:decimal, "~> 2.0 or ~> 3.0", [hex: :decimal, repo: "hexpm", optional: false]}, {:ecto, "~> 3.14", [hex: :ecto, repo: "hexpm", optional: false]}, {:ets, "~> 0.8", [hex: :ets, repo: "hexpm", optional: false]}, {:igniter, ">= 0.6.29 and < 1.0.0-0", [hex: :igniter, repo: "hexpm", optional: true]}, {:jason, ">= 1.0.0", [hex: :jason, repo: "hexpm", optional: false]}, {:picosat_elixir, "~> 0.2", [hex: :picosat_elixir, repo: "hexpm", optional: true]}, {:plug, ">= 0.0.0", [hex: :plug, repo: "hexpm", optional: true]}, {:reactor, "~> 1.0", [hex: :reactor, repo: "hexpm", optional: false]}, {:simple_sat, ">= 0.1.1 and < 1.0.0-0", [hex: :simple_sat, repo: "hexpm", optional: true]}, {:spark, ">= 2.6.0", [hex: :spark, repo: "hexpm", optional: false]}, {:splode, "~> 0.3", [hex: :splode, repo: "hexpm", optional: false]}, {:stream_data, "~> 1.0", [hex: :stream_data, repo: "hexpm", optional: false]}, {:telemetry, "~> 1.1", [hex: :telemetry, repo: "hexpm", optional: false]}], "hexpm", "7518ecf694e1b423478ddaa5baf713e9d38448df6873f3be6316f758bc6ab68d"},
  "crux": {:hex, :crux, "0.1.4", "1fa21f5ca886d3498f83871a3ef19379b80abf8cfcf2ed32007e80279e714f1e", [:mix], [{:picosat_elixir, "~> 0.2", [hex: :picosat_elixir, repo: "hexpm", optional: true]}, {:simple_sat, ">= 0.1.1 and < 1.0.0-0", [hex: :simple_sat, repo: "hexpm", optional: true]}, {:stream_data, "~> 1.0", [hex: :stream_data, repo: "hexpm", optional: true]}], "hexpm", "ff7d880cf732d82360aa81e439b8d4831cd30768061c9233f90c97e10162b9c0"},
  "decimal": {:hex, :decimal, "3.1.1", "430d87b04011ce6cbd4fd205be758311a81f87d552d40904abd00f015935b1d0", [:mix], [], "hexpm", "c5f25f2ced74a0587d03e6023f595db8e924c9d3922c8c8ffd9edfc4498cf1f6"},
  "ecto": {:hex, :ecto, "3.14.1", "7b740d87bdf45996aa0c2c2e081640906f10caa7ce5ba328fd294c7d49d0cc6f", [:mix], [{:decimal, "~> 3.0", [hex: :decimal, repo: "hexpm", optional: false]}, {:jason, "~> 1.0", [hex: :jason, repo: "hexpm", optional: true]}, {:telemetry, "~> 0.4 or ~> 1.0", [hex: :telemetry, repo: "hexpm", optional: false]}], "hexpm", "24b991956796700f467d0a3ef3d303138a3ef9ddddf8b98f43758ee067b20a30"},
  "ets": {:hex, :ets, "0.9.0", "79c6a6c205436780486f72d84230c6cba2f8a9920456750ddd1e47389107d5fd", [:mix], [], "hexpm", "2861fdfb04bcaeff370f1a5904eec864f0a56dcfebe5921ea9aadf2a481c822b"},
  "iterex": {:hex, :iterex, "0.1.2", "58f9b9b9a22a55cbfc7b5234a9c9c63eaac26d276b3db80936c0e1c60355a5a6", [:mix], [], "hexpm", "2e103b8bcc81757a9af121f6dc0df312c9a17220f302b1193ef720460d03029d"},
  "jason": {:hex, :jason, "1.4.5", "2e3a008590b0b8d7388c20293e9dcc9cf3e5d642fd2a114e4cbbb52e595d940a", [:mix], [{:decimal, "~> 1.0 or ~> 2.0 or ~> 3.0", [hex: :decimal, repo: "hexpm", optional: true]}], "hexpm", "b0c823996102bcd0239b3c2444eb00409b72f6a140c1950bc8b457d836b30684"},
  "multigraph": {:hex, :multigraph, "0.16.1-mg.4", "2bbe149f5411b0e3bf0624c7bf2e3da2738efeac2f9a67bbbcb807ab171f0a76", [:mix], [], "hexpm", "b9f3e2577cef4658eeedf97c76d22a86d33a7aab702a93c1da9c122e849e9037"},
  "reactor": {:hex, :reactor, "1.0.5", "43a3298fb5874248e72d61662704d5013194c427afcf740e14336f3379f53ed3", [:mix], [{:igniter, "~> 0.4", [hex: :igniter, repo: "hexpm", optional: true]}, {:iterex, "~> 0.1", [hex: :iterex, repo: "hexpm", optional: false]}, {:jason, "~> 1.0", [hex: :jason, repo: "hexpm", optional: false]}, {:multigraph, "~> 0.16.1-mg.2", [hex: :multigraph, repo: "hexpm", optional: false]}, {:spark, ">= 2.3.3 and < 3.0.0-0", [hex: :spark, repo: "hexpm", optional: false]}, {:splode, "~> 0.2", [hex: :splode, repo: "hexpm", optional: false]}, {:telemetry, "~> 1.2", [hex: :telemetry, repo: "hexpm", optional: false]}, {:yaml_elixir, "~> 2.11", [hex: :yaml_elixir, repo: "hexpm", optional: false]}, {:ymlr, "~> 5.0", [hex: :ymlr, repo: "hexpm", optional: false]}], "hexpm", "8867decb795d0b87a9dea5d146721af60312c0b45443d125d9be535946e8da19"},
  "spark": {:hex, :spark, "2.7.2", "36becc6ff03b40908cc821d403d7f06d893498e293d2f718afc6ca097fcb9d93", [:mix], [{:igniter, ">= 0.3.64 and < 1.0.0-0", [hex: :igniter, repo: "hexpm", optional: true]}, {:jason, "~> 1.4", [hex: :jason, repo: "hexpm", optional: true]}, {:sourceror, "~> 1.2", [hex: :sourceror, repo: "hexpm", optional: true]}], "hexpm", "adb323ddbf9dbbe326f9e5def54ac96c47911e852b2c270bb19a5147c56f1b45"},
  "splode": {:hex, :splode, "0.3.2", "7716b6b2260a98a6f018c65cc0393da2cdf17314202eb351a0956e8762190dff", [:mix], [], "hexpm", "08fd658f80da7f1cd254b149164dcff8acd44b22f032001d5416b97223d32bc9"},
  "stream_data": {:hex, :stream_data, "1.4.0", "026f929db613aabea6208012ae9b8970d3fd5f88b3bdf26831bc536f98c42036", [:mix], [], "hexpm", "2b0ee3a340dcce1c8cf6302a763ee757d1e01c54d6e16d9069062509d68b1dc9"},
  "telemetry": {:hex, :telemetry, "1.4.2", "a0cb522801dffb1c49fe6e30561badffc7b6d0e180db1300df759faa22062855", [:rebar3], [], "hexpm", "928f6495066506077862c0d1646609eed891a4326bee3126ba54b60af61febb1"},
  "yamerl": {:hex, :yamerl, "0.10.0", "4ff81fee2f1f6a46f1700c0d880b24d193ddb74bd14ef42cb0bcf46e81ef2f8e", [:rebar3], [], "hexpm", "346adb2963f1051dc837a2364e4acf6eb7d80097c0f53cbdc3046ec8ec4b4e6e"},
  "yaml_elixir": {:hex, :yaml_elixir, "2.12.2", "9dd1330fb4cd9a36a7b0f502e5b12486eff632792ee4a5f0eba52a4d4ec32c9c", [:mix], [{:yamerl, "~> 0.10", [hex: :yamerl, repo: "hexpm", optional: false]}], "hexpm", "e7c1b10122f973e6558462d51c39026ba0e14afbc6745318e990ea82cfe9e159"},
  "ymlr": {:hex, :ymlr, "5.1.6", "247479328fd5ea1e222ee59ecd5571ab2885cf1a6329aea458d4944cd035cfc1", [:mix], [], "hexpm", "b36d7c72384d2cb2094d2a3c8b0c3b12303e0ccd1b7b12333b81d75b1fe0b53a"},
}
EOF

RUN cat > /home/user/ledger/config/config.exs <<'EOF'
import Config

config :ledger, ash_domains: [Ledger.Billing]

config :logger, level: :warning
EOF

RUN cat > /home/user/ledger/lib/ledger/billing.ex <<'EOF'
defmodule Ledger.Billing do
  @moduledoc """
  The billing domain.
  """
  use Ash.Domain, otp_app: :ledger

  resources do
  end
end
EOF

RUN cat > /home/user/ledger/test/test_helper.exs <<'EOF'
ExUnit.start()
EOF

RUN cat > /home/user/ledger/.formatter.exs <<'EOF'
[
  import_deps: [:ash],
  inputs: ["{mix,.formatter}.exs", "{config,lib,test}/**/*.{ex,exs}"]
]
EOF

RUN cd /home/user/ledger && \
    mix deps.get && \
    MIX_ENV=dev mix deps.compile && \
    MIX_ENV=test mix deps.compile && \
    MIX_ENV=dev mix compile && \
    MIX_ENV=test mix compile && \
    rm -rf /tmp/mix_lock* && \
    chmod 1777 /tmp && \
    chmod -R a+rX /opt/mix /opt/hex

ENV HEX_OFFLINE=1

LABEL Author="generate-harbor-tasks"
LABEL Description="Offline Elixir 1.18.4 / OTP 27.3.4 environment with Ash 3.31.0 pre-compiled and an empty Ledger.Billing domain in /home/user/ledger."

CMD ["/bin/bash", "-c", "trap : TERM INT; sleep infinity & wait"]

# Container contents:
#   - always required apt packages: curl wget ca-certificates git python3 python3-pip python3-pytest bash ripgrep
#   - always required pip3 packages: pytest-json-ctrf
#   - Erlang/OTP 27.3.4 and Elixir 1.18.4 installed from builds.hex.pm into /opt/otp and /opt/elixir
#   - MIX_HOME=/opt/mix, HEX_HOME=/opt/hex, HEX_OFFLINE=1 so the image needs no network at solve time
#   - /home/user/ledger: mix project for the OTP app :ledger
#   - /home/user/ledger/mix.lock: every transitive dependency pinned by hash (ash 3.31.0, jason 1.4.5)
#   - /home/user/ledger/deps + _build/{dev,test}: dependencies fetched and compiled for both mix envs
#   - /home/user/ledger/lib/ledger/billing.ex: empty Ash domain registered in config/config.exs
#   - ash_money / ex_money are deliberately absent

COPY test_initial_state.py /bootstrap/test_initial_state.py

# Setup entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
