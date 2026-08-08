FROM ubuntu:24.04

ARG POCHI_VERSION

ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8
ENV OTP_VERSION=27.3.4
ENV ELIXIR_VERSION=1.18.4
ENV PATH=/opt/otp/bin:/opt/elixir/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
ENV MIX_HOME=/opt/mix
ENV HEX_HOME=/opt/hex
ENV ERL_AFLAGS="-kernel shell_history enabled"

RUN apt-get update -y && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        curl wget ca-certificates git python3 python3-pip python3-pytest bash ripgrep \
        unzip build-essential libncurses6 libssl-dev locales && \
    ln -s /usr/bin/python3 /usr/bin/python && \
    curl -fsSL https://getpochi.com/install.sh | bash -s ${POCHI_VERSION} && \
    ln -s /root/.pochi/bin/pochi /usr/local/bin/pochi && \
    pip3 install --break-system-packages pytest-json-ctrf requests pytest-xprocess && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Erlang/OTP and Elixir, pinned, from builds.hex.pm (arch aware: amd64 and arm64).
RUN arch="$(dpkg --print-architecture)" && \
    mkdir -p /opt/otp && \
    curl -fsSL "https://builds.hex.pm/builds/otp/${arch}/ubuntu-24.04/OTP-${OTP_VERSION}.tar.gz" \
      | tar -xz -C /opt/otp --strip-components=1 && \
    cd /opt/otp && ./Install -minimal /opt/otp && \
    mkdir -p /opt/elixir && \
    curl -fsSL -o /tmp/elixir.zip "https://builds.hex.pm/builds/elixir/v${ELIXIR_VERSION}-otp-27.zip" && \
    unzip -q /tmp/elixir.zip -d /opt/elixir && \
    rm /tmp/elixir.zip && \
    mkdir -p /opt/mix /opt/hex && \
    mix local.hex --force && \
    mix local.rebar --force && \
    chmod -R a+rX /opt/mix /opt/hex /opt/otp /opt/elixir

RUN mkdir -p /home/user && chmod 0755 /home/user

RUN mkdir -p /home/user/catalog/lib/catalog /home/user/catalog/config

RUN cat > /home/user/catalog/mix.exs <<'EOF'
defmodule Catalog.MixProject do
  use Mix.Project

  def project do
    [
      app: :catalog,
      version: "0.1.0",
      elixir: "~> 1.18",
      start_permanent: false,
      deps: deps()
    ]
  end

  def application do
    [
      extra_applications: [:logger],
      mod: {Catalog.Application, []}
    ]
  end

  defp deps do
    [
      {:ash, "~> 3.0"},
      {:ash_json_api, "~> 1.7"},
      {:open_api_spex, "~> 3.18"},
      {:plug, "~> 1.16"},
      {:bandit, "~> 1.5"},
      {:jason, "~> 1.4"},
      {:picosat_elixir, "~> 0.2"}
    ]
  end
end
EOF

RUN cat > /home/user/catalog/.formatter.exs <<'EOF'
[
  inputs: ["{mix,.formatter}.exs", "{config,lib,test}/**/*.{ex,exs}"]
]
EOF

RUN cat > /home/user/catalog/config/config.exs <<'EOF'
import Config

config :catalog, ash_domains: [Catalog.Library]

# JSON:API media type registration.
config :mime,
  extensions: %{"json" => "application/vnd.api+json"},
  types: %{"application/vnd.api+json" => ["json"]}

config :logger, level: :warning
EOF

RUN cat > /home/user/catalog/lib/catalog/application.ex <<'EOF'
defmodule Catalog.Application do
  @moduledoc false
  use Application

  @impl true
  def start(_type, _args) do
    children = []

    Supervisor.start_link(children, strategy: :one_for_one, name: Catalog.Supervisor)
  end
end
EOF

RUN cat > /home/user/catalog/mix.lock <<'EOF'
%{
  "ash": {:hex, :ash, "3.31.0", "9ccd7d5ff00a5329a33786063e4a3040681b61d736730cd7aa3f24e5843c1d4f", [:mix], [{:crux, ">= 0.1.2 and < 1.0.0-0", [hex: :crux, repo: "hexpm", optional: false]}, {:decimal, "~> 2.0 or ~> 3.0", [hex: :decimal, repo: "hexpm", optional: false]}, {:ecto, "~> 3.14", [hex: :ecto, repo: "hexpm", optional: false]}, {:ets, "~> 0.8", [hex: :ets, repo: "hexpm", optional: false]}, {:igniter, ">= 0.6.29 and < 1.0.0-0", [hex: :igniter, repo: "hexpm", optional: true]}, {:jason, ">= 1.0.0", [hex: :jason, repo: "hexpm", optional: false]}, {:picosat_elixir, "~> 0.2", [hex: :picosat_elixir, repo: "hexpm", optional: true]}, {:plug, ">= 0.0.0", [hex: :plug, repo: "hexpm", optional: true]}, {:reactor, "~> 1.0", [hex: :reactor, repo: "hexpm", optional: false]}, {:simple_sat, ">= 0.1.1 and < 1.0.0-0", [hex: :simple_sat, repo: "hexpm", optional: true]}, {:spark, ">= 2.6.0", [hex: :spark, repo: "hexpm", optional: false]}, {:splode, "~> 0.3", [hex: :splode, repo: "hexpm", optional: false]}, {:stream_data, "~> 1.0", [hex: :stream_data, repo: "hexpm", optional: false]}, {:telemetry, "~> 1.1", [hex: :telemetry, repo: "hexpm", optional: false]}], "hexpm", "7518ecf694e1b423478ddaa5baf713e9d38448df6873f3be6316f758bc6ab68d"},
  "ash_json_api": {:hex, :ash_json_api, "1.7.1", "d2f83d982dd15c0f246f46665f254678ac835a510bf8c2366132312183a2dc24", [:mix], [{:ash, ">= 3.19.1 and < 4.0.0-0", [hex: :ash, repo: "hexpm", optional: false]}, {:igniter, ">= 0.3.58 and < 1.0.0-0", [hex: :igniter, repo: "hexpm", optional: true]}, {:jason, "~> 1.1", [hex: :jason, repo: "hexpm", optional: false]}, {:json_xema, "~> 0.4", [hex: :json_xema, repo: "hexpm", optional: false]}, {:open_api_spex, "~> 3.16", [hex: :open_api_spex, repo: "hexpm", optional: true]}, {:phoenix, "~> 1.6", [hex: :phoenix, repo: "hexpm", optional: false]}, {:plug, "~> 1.11", [hex: :plug, repo: "hexpm", optional: false]}, {:spark, ">= 2.2.10", [hex: :spark, repo: "hexpm", optional: false]}], "hexpm", "0ff72b51d99c93f7ee655d2d5e10b29f5561ad36a0ee11dadcbcec7a4b995368"},
  "bandit": {:hex, :bandit, "1.12.4", "10bbab488edf8162318d736c19c5837077b8fca2bf5d95b07b33830387124f62", [:mix], [{:hpax, "~> 1.0", [hex: :hpax, repo: "hexpm", optional: false]}, {:plug, "~> 1.18", [hex: :plug, repo: "hexpm", optional: false]}, {:telemetry, "~> 0.4 or ~> 1.0", [hex: :telemetry, repo: "hexpm", optional: false]}, {:thousand_island, "~> 1.5", [hex: :thousand_island, repo: "hexpm", optional: false]}, {:websock, "~> 0.5", [hex: :websock, repo: "hexpm", optional: false]}], "hexpm", "84513318c5752a2a8017664450f889b47fae5d53d64698ddf1e4fb09a7449e8d"},
  "conv_case": {:hex, :conv_case, "0.2.3", "c1455c27d3c1ffcdd5f17f1e91f40b8a0bc0a337805a6e8302f441af17118ed8", [:mix], [], "hexpm", "88f29a3d97d1742f9865f7e394ed3da011abb7c5e8cc104e676fdef6270d4b4a"},
  "crux": {:hex, :crux, "0.1.4", "1fa21f5ca886d3498f83871a3ef19379b80abf8cfcf2ed32007e80279e714f1e", [:mix], [{:picosat_elixir, "~> 0.2", [hex: :picosat_elixir, repo: "hexpm", optional: true]}, {:simple_sat, ">= 0.1.1 and < 1.0.0-0", [hex: :simple_sat, repo: "hexpm", optional: true]}, {:stream_data, "~> 1.0", [hex: :stream_data, repo: "hexpm", optional: true]}], "hexpm", "ff7d880cf732d82360aa81e439b8d4831cd30768061c9233f90c97e10162b9c0"},
  "decimal": {:hex, :decimal, "3.1.1", "430d87b04011ce6cbd4fd205be758311a81f87d552d40904abd00f015935b1d0", [:mix], [], "hexpm", "c5f25f2ced74a0587d03e6023f595db8e924c9d3922c8c8ffd9edfc4498cf1f6"},
  "ecto": {:hex, :ecto, "3.14.1", "7b740d87bdf45996aa0c2c2e081640906f10caa7ce5ba328fd294c7d49d0cc6f", [:mix], [{:decimal, "~> 3.0", [hex: :decimal, repo: "hexpm", optional: false]}, {:jason, "~> 1.0", [hex: :jason, repo: "hexpm", optional: true]}, {:telemetry, "~> 0.4 or ~> 1.0", [hex: :telemetry, repo: "hexpm", optional: false]}], "hexpm", "24b991956796700f467d0a3ef3d303138a3ef9ddddf8b98f43758ee067b20a30"},
  "elixir_make": {:hex, :elixir_make, "0.10.0", "16577e2583a79bb79237bbff349619ef5d80afffc07eac6e4faf0d00e2ddaf7d", [:mix], [], "hexpm", "dc1f09fb7fa68866b886abd5f0f3c83553b1a19a52359a899e92af1bb3b31982"},
  "ets": {:hex, :ets, "0.9.0", "79c6a6c205436780486f72d84230c6cba2f8a9920456750ddd1e47389107d5fd", [:mix], [], "hexpm", "2861fdfb04bcaeff370f1a5904eec864f0a56dcfebe5921ea9aadf2a481c822b"},
  "hpax": {:hex, :hpax, "1.0.4", "777de5d433b0fbdc7c418159c8055910faa8047ffdb3d6b31098d2a46cd7685c", [:mix], [], "hexpm", "afc7cb142ebcc2d01ce7816190b98ce5dd49e799111b24249f3443d730f377ca"},
  "iterex": {:hex, :iterex, "0.1.2", "58f9b9b9a22a55cbfc7b5234a9c9c63eaac26d276b3db80936c0e1c60355a5a6", [:mix], [], "hexpm", "2e103b8bcc81757a9af121f6dc0df312c9a17220f302b1193ef720460d03029d"},
  "jason": {:hex, :jason, "1.4.5", "2e3a008590b0b8d7388c20293e9dcc9cf3e5d642fd2a114e4cbbb52e595d940a", [:mix], [{:decimal, "~> 1.0 or ~> 2.0 or ~> 3.0", [hex: :decimal, repo: "hexpm", optional: true]}], "hexpm", "b0c823996102bcd0239b3c2444eb00409b72f6a140c1950bc8b457d836b30684"},
  "json_xema": {:hex, :json_xema, "0.6.5", "060459c9c9152650edb4427b1acbc61fa43a23bcea0301d200cafa76e0880f37", [:mix], [{:conv_case, "~> 0.2", [hex: :conv_case, repo: "hexpm", optional: false]}, {:xema, "~> 0.16", [hex: :xema, repo: "hexpm", optional: false]}], "hexpm", "b8ffdbc2f67aa8b91b44e1ba0ab77eb5c0b0142116f8fbb804977fb939d470ef"},
  "mime": {:hex, :mime, "2.0.7", "b8d739037be7cd402aee1ba0306edfdef982687ee7e9859bee6198c1e7e2f128", [:mix], [], "hexpm", "6171188e399ee16023ffc5b76ce445eb6d9672e2e241d2df6050f3c771e80ccd"},
  "multigraph": {:hex, :multigraph, "0.16.1-mg.4", "2bbe149f5411b0e3bf0624c7bf2e3da2738efeac2f9a67bbbcb807ab171f0a76", [:mix], [], "hexpm", "b9f3e2577cef4658eeedf97c76d22a86d33a7aab702a93c1da9c122e849e9037"},
  "open_api_spex": {:hex, :open_api_spex, "3.22.3", "0e383bf23cc3a060bffaebbcd09fc06bfc908d948c00e518aed36bbf8a2fe473", [:mix], [{:decimal, "~> 1.0 or ~> 2.0 or ~> 3.0", [hex: :decimal, repo: "hexpm", optional: true]}, {:jason, "~> 1.0", [hex: :jason, repo: "hexpm", optional: true]}, {:plug, "~> 1.7", [hex: :plug, repo: "hexpm", optional: false]}, {:poison, "~> 3.0 or ~> 4.0 or ~> 5.0 or ~> 6.0", [hex: :poison, repo: "hexpm", optional: true]}, {:ymlr, "~> 2.0 or ~> 3.0 or ~> 4.0 or ~> 5.0", [hex: :ymlr, repo: "hexpm", optional: true]}], "hexpm", "5f74f1878fdc38f8e961b0b943ac7af88dcf3a82a0c0ef6680ddfd3d161aecbd"},
  "phoenix": {:hex, :phoenix, "1.8.9", "a63ed0962ed5b903b146dab0ae8eb8387fe478f8171a5e26d56a165f35996fe1", [:mix], [{:bandit, "~> 1.0", [hex: :bandit, repo: "hexpm", optional: true]}, {:jason, "~> 1.0", [hex: :jason, repo: "hexpm", optional: true]}, {:phoenix_pubsub, "~> 2.1", [hex: :phoenix_pubsub, repo: "hexpm", optional: false]}, {:phoenix_template, "~> 1.0", [hex: :phoenix_template, repo: "hexpm", optional: false]}, {:phoenix_view, "~> 2.0", [hex: :phoenix_view, repo: "hexpm", optional: true]}, {:plug, "~> 1.14", [hex: :plug, repo: "hexpm", optional: false]}, {:plug_cowboy, "~> 2.7", [hex: :plug_cowboy, repo: "hexpm", optional: true]}, {:plug_crypto, "~> 1.2 or ~> 2.0", [hex: :plug_crypto, repo: "hexpm", optional: false]}, {:telemetry, "~> 0.4 or ~> 1.0", [hex: :telemetry, repo: "hexpm", optional: false]}, {:websock_adapter, "~> 0.5", [hex: :websock_adapter, repo: "hexpm", optional: false]}], "hexpm", "3477e2dd5a4f61820341169031bdfe21275f659923bea9c5c0ea2aa1c3fcc046"},
  "phoenix_pubsub": {:hex, :phoenix_pubsub, "2.2.0", "ff3a5616e1bed6804de7773b92cbccfc0b0f473faf1f63d7daf1206c7aeaaa6f", [:mix], [], "hexpm", "adc313a5bf7136039f63cfd9668fde73bba0765e0614cba80c06ac9460ff3e96"},
  "phoenix_template": {:hex, :phoenix_template, "1.0.4", "e2092c132f3b5e5b2d49c96695342eb36d0ed514c5b252a77048d5969330d639", [:mix], [{:phoenix_html, "~> 2.14.2 or ~> 3.0 or ~> 4.0", [hex: :phoenix_html, repo: "hexpm", optional: true]}], "hexpm", "2c0c81f0e5c6753faf5cca2f229c9709919aba34fab866d3bc05060c9c444206"},
  "picosat_elixir": {:hex, :picosat_elixir, "0.2.3", "bf326d0f179fbb3b706bb2c15fbc367dacfa2517157d090fdfc32edae004c597", [:make, :mix], [{:elixir_make, "~> 0.6", [hex: :elixir_make, repo: "hexpm", optional: false]}], "hexpm", "f76c9db2dec9d2561ffaa9be35f65403d53e984e8cd99c832383b7ab78c16c66"},
  "plug": {:hex, :plug, "1.20.3", "56c480c633ec2ce10140e236e15233bf576e1d323887d7c96711bd02ab5160db", [:mix], [{:mime, "~> 1.0 or ~> 2.0", [hex: :mime, repo: "hexpm", optional: false]}, {:plug_crypto, "~> 1.1.1 or ~> 1.2 or ~> 2.0", [hex: :plug_crypto, repo: "hexpm", optional: false]}, {:telemetry, "~> 0.4.3 or ~> 1.0", [hex: :telemetry, repo: "hexpm", optional: false]}], "hexpm", "be266aee1b8536ef6409d58cf39a3121319f0ec47cfa1b24024485aa0e76ad76"},
  "plug_crypto": {:hex, :plug_crypto, "2.2.0", "144014737daaf485407f5ed77daeaad74d651b216a28c87543f8cc7043f8efc8", [:mix], [], "hexpm", "83a95744ab1c75876542b6fab135fcc176280e0f301a111c1f757fddcec95d2c"},
  "reactor": {:hex, :reactor, "1.0.5", "43a3298fb5874248e72d61662704d5013194c427afcf740e14336f3379f53ed3", [:mix], [{:igniter, "~> 0.4", [hex: :igniter, repo: "hexpm", optional: true]}, {:iterex, "~> 0.1", [hex: :iterex, repo: "hexpm", optional: false]}, {:jason, "~> 1.0", [hex: :jason, repo: "hexpm", optional: false]}, {:multigraph, "~> 0.16.1-mg.2", [hex: :multigraph, repo: "hexpm", optional: false]}, {:spark, ">= 2.3.3 and < 3.0.0-0", [hex: :spark, repo: "hexpm", optional: false]}, {:splode, "~> 0.2", [hex: :splode, repo: "hexpm", optional: false]}, {:telemetry, "~> 1.2", [hex: :telemetry, repo: "hexpm", optional: false]}, {:yaml_elixir, "~> 2.11", [hex: :yaml_elixir, repo: "hexpm", optional: false]}, {:ymlr, "~> 5.0", [hex: :ymlr, repo: "hexpm", optional: false]}], "hexpm", "8867decb795d0b87a9dea5d146721af60312c0b45443d125d9be535946e8da19"},
  "spark": {:hex, :spark, "2.7.2", "36becc6ff03b40908cc821d403d7f06d893498e293d2f718afc6ca097fcb9d93", [:mix], [{:igniter, ">= 0.3.64 and < 1.0.0-0", [hex: :igniter, repo: "hexpm", optional: true]}, {:jason, "~> 1.4", [hex: :jason, repo: "hexpm", optional: true]}, {:sourceror, "~> 1.2", [hex: :sourceror, repo: "hexpm", optional: true]}], "hexpm", "adb323ddbf9dbbe326f9e5def54ac96c47911e852b2c270bb19a5147c56f1b45"},
  "splode": {:hex, :splode, "0.3.2", "7716b6b2260a98a6f018c65cc0393da2cdf17314202eb351a0956e8762190dff", [:mix], [], "hexpm", "08fd658f80da7f1cd254b149164dcff8acd44b22f032001d5416b97223d32bc9"},
  "stream_data": {:hex, :stream_data, "1.4.0", "026f929db613aabea6208012ae9b8970d3fd5f88b3bdf26831bc536f98c42036", [:mix], [], "hexpm", "2b0ee3a340dcce1c8cf6302a763ee757d1e01c54d6e16d9069062509d68b1dc9"},
  "telemetry": {:hex, :telemetry, "1.4.2", "a0cb522801dffb1c49fe6e30561badffc7b6d0e180db1300df759faa22062855", [:rebar3], [], "hexpm", "928f6495066506077862c0d1646609eed891a4326bee3126ba54b60af61febb1"},
  "thousand_island": {:hex, :thousand_island, "1.5.0", "f50a213cac97262b6d5ebb85745aa2c00fec1413191e6e66834788d45425cecb", [:mix], [{:telemetry, "~> 0.4 or ~> 1.0", [hex: :telemetry, repo: "hexpm", optional: false]}], "hexpm", "708923d40523e43cf99041ab37a0d4b0ec426ac6438fa3716ab23d919eaeb412"},
  "websock": {:hex, :websock, "0.5.3", "2f69a6ebe810328555b6fe5c831a851f485e303a7c8ce6c5f675abeb20ebdadc", [:mix], [], "hexpm", "6105453d7fac22c712ad66fab1d45abdf049868f253cf719b625151460b8b453"},
  "websock_adapter": {:hex, :websock_adapter, "0.6.0", "73db5ab8aaefd1a876a97ce3e6afc96562625de69ef17a4e04426e034849d0b8", [:mix], [{:bandit, ">= 0.6.0", [hex: :bandit, repo: "hexpm", optional: true]}, {:plug, "~> 1.14", [hex: :plug, repo: "hexpm", optional: false]}, {:plug_cowboy, "~> 2.6", [hex: :plug_cowboy, repo: "hexpm", optional: true]}, {:websock, "~> 0.5", [hex: :websock, repo: "hexpm", optional: false]}], "hexpm", "50021a85bce8f203b086705d9e0c5415e2c7eb05d319111b0428fe71f9934617"},
  "xema": {:hex, :xema, "0.17.9", "10bd9eae3fdcdd810229afc53fe7fb87026141d5081965fe10eddc203299ca74", [:mix], [{:conv_case, "~> 0.2.2", [hex: :conv_case, repo: "hexpm", optional: false]}, {:decimal, "~> 1.0 or ~> 2.0 or ~> 3.0", [hex: :decimal, repo: "hexpm", optional: true]}], "hexpm", "5cb8757c006ee57423fc8f076f3289377dedce9baeb93d1997d6f19d5cee73a8"},
  "yamerl": {:hex, :yamerl, "0.10.0", "4ff81fee2f1f6a46f1700c0d880b24d193ddb74bd14ef42cb0bcf46e81ef2f8e", [:rebar3], [], "hexpm", "346adb2963f1051dc837a2364e4acf6eb7d80097c0f53cbdc3046ec8ec4b4e6e"},
  "yaml_elixir": {:hex, :yaml_elixir, "2.12.2", "9dd1330fb4cd9a36a7b0f502e5b12486eff632792ee4a5f0eba52a4d4ec32c9c", [:mix], [{:yamerl, "~> 0.10", [hex: :yamerl, repo: "hexpm", optional: false]}], "hexpm", "e7c1b10122f973e6558462d51c39026ba0e14afbc6745318e990ea82cfe9e159"},
  "ymlr": {:hex, :ymlr, "5.1.6", "247479328fd5ea1e222ee59ecd5571ab2885cf1a6329aea458d4944cd035cfc1", [:mix], [], "hexpm", "b36d7c72384d2cb2094d2a3c8b0c3b12303e0ccd1b7b12333b81d75b1fe0b53a"},
}
EOF

# Vendor and precompile every dependency for both dev and test, then go offline.
RUN cd /home/user/catalog && \
    mix deps.get && \
    MIX_ENV=dev mix deps.compile && \
    MIX_ENV=dev mix compile && \
    MIX_ENV=test mix deps.compile && \
    MIX_ENV=test mix compile && \
    rm -rf /tmp/mix_lock* && \
    chmod 1777 /tmp && \
    chmod -R a+rwX /home/user/catalog

ENV HEX_OFFLINE=1
ENV MIX_ENV=dev

LABEL Author="generate-harbor-tasks"
LABEL Description="Offline Elixir 1.18.4 / OTP 27.3.4 environment with an empty :catalog Mix project whose Ash 3.31 + ash_json_api 1.7 dependency tree is pre-compiled for dev and test."

CMD ["/bin/bash", "-c", "trap : TERM INT; sleep infinity & wait"]

# Container contents:
#   - always required apt packages: curl wget ca-certificates git python3 python3-pip python3-pytest bash ripgrep
#   - always required pip3 packages: pytest-json-ctrf
#   - extra pip3 packages: requests, pytest-xprocess (used by the final-state HTTP tests)
#   - Erlang/OTP 27.3.4 in /opt/otp and Elixir 1.18.4 in /opt/elixir (pinned builds.hex.pm tarballs)
#   - MIX_HOME=/opt/mix, HEX_HOME=/opt/hex, HEX_OFFLINE=1 so no Hex access is needed at solve time
#   - /home/user/catalog: empty :catalog Mix project (mix.exs, mix.lock, config/config.exs,
#     lib/catalog/application.ex) with deps/ vendored and _build/{dev,test} fully compiled

COPY test_initial_state.py /bootstrap/test_initial_state.py

# Setup entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
