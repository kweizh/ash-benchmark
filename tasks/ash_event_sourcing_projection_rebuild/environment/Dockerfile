FROM ubuntu:24.04

ARG POCHI_VERSION
ARG OTP_VERSION=27.3.4
ARG ELIXIR_VERSION=1.18.4

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8

RUN apt-get update -y && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        curl wget ca-certificates git python3 python3-pip python3-pytest bash ripgrep \
        unzip libncurses6 libssl3t64 procps && \
    ln -s /usr/bin/python3 /usr/bin/python && \
    curl -fsSL https://getpochi.com/install.sh | bash -s ${POCHI_VERSION} && \
    ln -s /root/.pochi/bin/pochi /usr/local/bin/pochi && \
    pip3 install --break-system-packages pytest-json-ctrf && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# --- Erlang/OTP + Elixir, pinned, from the official Hex build server ---------
RUN arch="$(dpkg --print-architecture)" && \
    mkdir -p /opt/otp && \
    curl -fsSL --retry 8 --retry-delay 5 --retry-all-errors -o /tmp/otp.tar.gz \
      "https://builds.hex.pm/builds/otp/${arch}/ubuntu-24.04/OTP-${OTP_VERSION}.tar.gz" && \
    tar -xzf /tmp/otp.tar.gz -C /opt/otp --strip-components=1 && \
    cd /opt/otp && ./Install -minimal /opt/otp && \
    rm -f /tmp/otp.tar.gz && \
    mkdir -p /opt/elixir && \
    curl -fsSL --retry 8 --retry-delay 5 --retry-all-errors -o /tmp/elixir.zip \
      "https://builds.hex.pm/builds/elixir/v${ELIXIR_VERSION}-otp-27.zip" && \
    unzip -q /tmp/elixir.zip -d /opt/elixir && \
    rm -f /tmp/elixir.zip

ENV PATH="/opt/otp/bin:/opt/elixir/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin" \
    MIX_HOME=/opt/mix \
    HEX_HOME=/opt/hex

RUN mkdir -p /opt/mix /opt/hex && \
    (for i in 1 2 3 4 5 6; do mix local.hex --force && exit 0; sleep 10; done; exit 1) && \
    (for i in 1 2 3 4 5 6; do mix local.rebar --force && exit 0; sleep 10; done; exit 1) && \
    chmod -R a+rX /opt/mix /opt/hex

RUN mkdir -p /home/user && chmod 0755 /home/user

# --- Scaffold project --------------------------------------------------------
RUN mkdir -p /home/user/vault/config /home/user/vault/lib/vault/ledger

RUN cat > /home/user/vault/mix.exs <<'EOF'
defmodule Vault.MixProject do
  use Mix.Project

  def project do
    [
      app: :vault,
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
      mod: {Vault.Application, []}
    ]
  end

  defp deps do
    [
      {:ash, "~> 3.31"}
    ]
  end
end
EOF

RUN cat > /home/user/vault/config/config.exs <<'EOF'
import Config

# The Vault.Ledger domain must be implemented by you.
config :vault, ash_domains: [Vault.Ledger]

config :logger, level: :warning
EOF

RUN cat > /home/user/vault/lib/vault/application.ex <<'EOF'
defmodule Vault.Application do
  @moduledoc false
  use Application

  @impl true
  def start(_type, _args) do
    Supervisor.start_link([], strategy: :one_for_one, name: Vault.Supervisor)
  end
end
EOF

RUN cat > /home/user/vault/lib/vault/ledger/hook.ex <<'EOF'
defmodule Vault.Ledger.Hook do
  @moduledoc """
  A test seam used by the evaluation suite to interleave work into long running
  operations, and to observe that those operations reached a documented point.

  `run/1` records that the labelled point was reached and, if a callback has been
  registered for that label in the current process, invokes it.

  Do not modify this module.
  """

  @doc "Register a zero-arity callback to be invoked the next time `run/1` is called with `label`."
  @spec set(atom(), (-> any())) :: :ok
  def set(label, fun) when is_atom(label) and is_function(fun, 0) do
    Process.put({__MODULE__, :callback, label}, fun)
    :ok
  end

  @doc "Remove any callback registered for `label` and reset its invocation counter."
  @spec clear(atom()) :: :ok
  def clear(label) when is_atom(label) do
    Process.delete({__MODULE__, :callback, label})
    Process.delete({__MODULE__, :count, label})
    :ok
  end

  @doc "How many times `run/1` has been called with `label` in this process."
  @spec count(atom()) :: non_neg_integer()
  def count(label) when is_atom(label) do
    Process.get({__MODULE__, :count, label}, 0)
  end

  @doc "Mark the labelled point as reached and invoke the registered callback, if any."
  @spec run(atom()) :: :ok
  def run(label) when is_atom(label) do
    Process.put({__MODULE__, :count, label}, count(label) + 1)

    case Process.get({__MODULE__, :callback, label}) do
      fun when is_function(fun, 0) -> fun.()
      _ -> :ok
    end

    :ok
  end
end
EOF

RUN cat > /home/user/vault/README.md <<'EOF'
# vault

An event-sourced account ledger built on Ash Framework v3 with the in-memory ETS
data layer.

The project ships only the OTP application module and `Vault.Ledger.Hook`. The
`Vault.Ledger` domain, its resources and the event-sourcing modules are yours to
write.

Useful commands (the container is offline; all dependencies are already fetched
and compiled):

    mix compile
    mix run <script.exs>
EOF

# --- Pre-fetch and pre-compile every dependency so the image works offline ---
RUN cd /home/user/vault && \
    (for i in 1 2 3 4 5 6; do mix deps.get && exit 0; sleep 10; done; exit 1) && \
    MIX_ENV=dev mix deps.compile && \
    MIX_ENV=dev mix compile && \
    rm -rf /tmp/mix_lock* /tmp/mix_pubsub* && \
    chmod 1777 /tmp && \
    chmod -R a+rwX /home/user/vault && \
    chown -R 1000:1000 /home/user/vault

ENV HEX_OFFLINE=1

LABEL Author="generate-harbor-tasks"
LABEL Description="Elixir 1.18 / OTP 27 image with Ash 3.31 pre-compiled and a bare Vault event-sourcing scaffold at /home/user/vault."

CMD ["/bin/bash", "-c", "trap : TERM INT; sleep infinity & wait"]

# Container contents:
#   - always required apt packages: curl wget ca-certificates git python3 python3-pip python3-pytest bash ripgrep
#   - always required pip3 packages: pytest-json-ctrf
#   - Erlang/OTP 27.3.4 and Elixir 1.18.4 installed from builds.hex.pm into /opt
#   - Hex and rebar3 installed into /opt/mix and /opt/hex (world readable)
#   - /home/user/vault: Mix project with the `ash ~> 3.31` dependency fetched,
#     compiled and pinned in mix.lock; HEX_OFFLINE=1 so no network is needed
#   - /home/user/vault/lib/vault/application.ex: OTP application module (scaffold)
#   - /home/user/vault/lib/vault/ledger/hook.ex: Vault.Ledger.Hook test seam (scaffold)
#   - /home/user/vault/config/config.exs: lists the (not yet written) Vault.Ledger domain

COPY test_initial_state.py /bootstrap/test_initial_state.py

# Setup entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
