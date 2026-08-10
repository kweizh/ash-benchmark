FROM ubuntu:24.04

ARG POCHI_VERSION
ARG OTP_VERSION=27.3.4
ARG ELIXIR_VERSION=1.18.4

RUN apt-get update -y && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        curl wget ca-certificates git python3 python3-pip python3-pytest bash ripgrep \
        unzip locales procps libncurses6 postgresql postgresql-contrib && \
    ln -s /usr/bin/python3 /usr/bin/python && \
    curl -fsSL https://getpochi.com/install.sh | bash -s ${POCHI_VERSION} && \
    ln -s /root/.pochi/bin/pochi /usr/local/bin/pochi && \
    pip3 install --break-system-packages pytest-json-ctrf && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

ENV LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PATH=/opt/otp/bin:/opt/elixir/bin:/usr/lib/postgresql/16/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

# ---------------------------------------------------------------- OTP 27.3.4 --
RUN arch="$(dpkg --print-architecture)" && \
    curl -fsSL --retry 8 --retry-delay 5 --retry-all-errors \
        -o /tmp/otp.tar.gz "https://builds.hex.pm/builds/otp/${arch}/ubuntu-24.04/OTP-${OTP_VERSION}.tar.gz" && \
    mkdir -p /opt/otp && \
    tar -xzf /tmp/otp.tar.gz -C /opt/otp --strip-components=1 && \
    rm -f /tmp/otp.tar.gz && \
    cd /opt/otp && ./Install -minimal /opt/otp && \
    erl -noshell -eval 'io:format("OTP ~s~n",[erlang:system_info(otp_release)]),halt().'

# ------------------------------------------------------------- Elixir 1.18.4 --
RUN curl -fsSL --retry 8 --retry-delay 5 --retry-all-errors \
        -o /tmp/elixir.zip "https://builds.hex.pm/builds/elixir/v${ELIXIR_VERSION}-otp-27.zip" && \
    mkdir -p /opt/elixir && \
    unzip -q /tmp/elixir.zip -d /opt/elixir && \
    rm -f /tmp/elixir.zip && \
    elixir --version

ENV MIX_HOME=/opt/mix \
    HEX_HOME=/opt/hex \
    MIX_ENV=dev

RUN mkdir -p /opt/mix /opt/hex && \
    (for i in 1 2 3 4 5 6; do mix local.hex --force && break || sleep 10; done) && \
    (for i in 1 2 3 4 5 6; do mix local.rebar --force && break || sleep 10; done) && \
    chmod -R a+rX /opt/mix /opt/hex

# ------------------------------------------ local PostgreSQL 16 (no network) --
RUN mkdir -p /srv/pgdata && \
    chown -R 1000:1000 /srv/pgdata && \
    su ubuntu -c "/usr/lib/postgresql/16/bin/initdb -D /srv/pgdata -U postgres --auth-local=trust --auth-host=trust --encoding=UTF8 --locale=C" && \
    printf '%s\n' \
        "listen_addresses = '127.0.0.1'" \
        "port = 5432" \
        "unix_socket_directories = '/tmp'" \
        "fsync = off" \
        "synchronous_commit = off" \
        "full_page_writes = off" \
        "max_connections = 100" \
        "shared_buffers = 64MB" \
        "log_min_messages = warning" \
        >> /srv/pgdata/postgresql.conf && \
    chown 1000:1000 /srv/pgdata/postgresql.conf

RUN cat > /usr/local/bin/pg-start <<'PGEOF'
#!/bin/sh
# Starts the in-container PostgreSQL 16 server and blocks until it accepts
# connections on 127.0.0.1:5432. Safe to call repeatedly.
PGDATA=/srv/pgdata
export PGDATA
if pg_isready -h 127.0.0.1 -p 5432 -q 2>/dev/null; then
  exit 0
fi
if [ "$(id -u)" = "0" ]; then
  su ubuntu -c "/usr/lib/postgresql/16/bin/pg_ctl -D /srv/pgdata -l /srv/pgdata/server.log -w -t 60 start" >/dev/null 2>&1 || true
else
  /usr/lib/postgresql/16/bin/pg_ctl -D /srv/pgdata -l /srv/pgdata/server.log -w -t 60 start >/dev/null 2>&1 || true
fi
i=0
while [ "$i" -lt 90 ]; do
  if pg_isready -h 127.0.0.1 -p 5432 -q 2>/dev/null; then
    exit 0
  fi
  i=$((i+1))
  sleep 1
done
echo "postgres did not become ready" >&2
if [ -f /srv/pgdata/server.log ]; then tail -n 50 /srv/pgdata/server.log >&2; fi
exit 1
PGEOF

RUN chmod 0755 /usr/local/bin/pg-start

RUN mkdir -p /home/user && chmod 0755 /home/user

# ------------------------------------------------------ logistics scaffold ----
RUN mkdir -p /home/user/logistics/config \
             /home/user/logistics/lib/logistics/freight \
             /home/user/logistics/priv/repo/migrations

RUN cat > /home/user/logistics/mix.exs <<'EOF'
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
EOF

RUN cat > /home/user/logistics/config/config.exs <<'EOF'
import Config

config :logistics,
  ecto_repos: [Logistics.Repo],
  ash_domains: [Logistics.Freight]

config :logistics, Logistics.Repo,
  username: "postgres",
  password: "postgres",
  hostname: "127.0.0.1",
  port: 5432,
  database: "logistics_dev",
  pool_size: 10

config :logger, level: :warning

config :ash, :missed_notifications, :ignore
EOF

RUN cat > /home/user/logistics/lib/logistics/application.ex <<'EOF'
defmodule Logistics.Application do
  @moduledoc false

  use Application

  @impl true
  def start(_type, _args) do
    children = [
      Logistics.Repo
    ]

    Supervisor.start_link(children, strategy: :one_for_one, name: Logistics.Supervisor)
  end
end
EOF

RUN cd /home/user/logistics && \
    (for i in 1 2 3 4 5 6; do mix deps.get && break || sleep 10; done) && \
    mix deps.compile && \
    mix compile && \
    rm -rf /tmp/mix_lock* /tmp/mix_pubsub* && \
    chmod 1777 /tmp && \
    chown -R 1000:1000 /home/user && \
    chmod -R a+rwX /home/user

ENV HEX_OFFLINE=1

LABEL Author="generate-harbor-tasks"
LABEL Description="Offline Elixir 1.18.4 / OTP 27.3.4 image with ash 3.31 + ash_postgres 2.11, an in-container PostgreSQL 16 server, and an empty :logistics Mix project at /home/user/logistics."

CMD ["/bin/bash", "-c", "trap : TERM INT; sleep infinity & wait"]

# Container contents:
#   - always required apt packages: curl wget ca-certificates git python3 python3-pip python3-pytest bash ripgrep
#   - always required pip3 packages: pytest-json-ctrf
#   - Pochi CLI at /usr/local/bin/pochi
#   - Erlang/OTP 27.3.4 at /opt/otp and Elixir 1.18.4 at /opt/elixir (builds.hex.pm, arch aware)
#   - Hex/rebar in /opt/hex and /opt/mix; HEX_OFFLINE=1 after the dependency layer
#   - PostgreSQL 16 server + contrib (citext, uuid-ossp) with a cluster initialised at
#     /srv/pgdata and a /usr/local/bin/pg-start helper that starts it as uid 1000 and
#     waits for readiness on 127.0.0.1:5432
#   - /home/user/logistics: empty Mix project (:logistics) with mix.exs, mix.lock,
#     config/config.exs, lib/logistics/application.ex, an empty priv/repo/migrations,
#     and deps/ + _build/ prepopulated for ash 3.31.0 and ash_postgres 2.11.0

COPY test_initial_state.py /bootstrap/test_initial_state.py

# Setup entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
