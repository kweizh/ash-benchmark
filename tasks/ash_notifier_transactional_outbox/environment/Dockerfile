FROM ubuntu:24.04

ARG POCHI_VERSION
ARG OTP_VERSION=27.3.4
ARG ELIXIR_VERSION=1.18.4

ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=C.UTF-8
ENV MIX_HOME=/opt/mix
ENV HEX_HOME=/opt/hex
ENV PATH=/opt/otp/bin:/opt/elixir/bin:/opt/mix/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin

RUN apt-get update -y && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        curl wget ca-certificates git python3 python3-pip python3-pytest bash ripgrep \
        unzip xz-utils libncurses6 libssl3t64 locales && \
    ln -s /usr/bin/python3 /usr/bin/python && \
    curl -fsSL https://getpochi.com/install.sh | bash -s ${POCHI_VERSION} && \
    ln -s /root/.pochi/bin/pochi /usr/local/bin/pochi && \
    pip3 install --break-system-packages pytest-json-ctrf && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Erlang/OTP + Elixir from the official hex.pm builds (arch aware, no third-party apt repo).
RUN mkdir -p /opt/otp /opt/elixir && \
    curl -fsSL -o /tmp/otp.tar.gz \
      "https://builds.hex.pm/builds/otp/$(dpkg --print-architecture)/ubuntu-24.04/OTP-${OTP_VERSION}.tar.gz" && \
    tar -xzf /tmp/otp.tar.gz -C /opt/otp --strip-components=1 && \
    rm /tmp/otp.tar.gz && \
    cd /opt/otp && ./Install -minimal /opt/otp && \
    curl -fsSL -o /tmp/elixir.zip \
      "https://builds.hex.pm/builds/elixir/v${ELIXIR_VERSION}-otp-27.zip" && \
    unzip -q /tmp/elixir.zip -d /opt/elixir && \
    rm /tmp/elixir.zip && \
    erl -noshell -eval 'io:format("~s~n", [erlang:system_info(otp_release)]), halt().' && \
    elixir --version

RUN mkdir -p /opt/mix /opt/hex && \
    mix local.hex --force && \
    mix local.rebar --force && \
    chmod -R a+rwX /opt/mix /opt/hex

RUN mkdir -p /home/user && chmod 0755 /home/user
RUN mkdir -p /home/user/outbox/config /home/user/outbox/lib/outbox/ledger

RUN cat > /home/user/outbox/mix.exs <<'EOF'
defmodule Outbox.MixProject do
  use Mix.Project

  def project do
    [
      app: :outbox,
      version: "0.1.0",
      elixir: "~> 1.18",
      start_permanent: false,
      deps: deps()
    ]
  end

  def application do
    [
      extra_applications: [:logger],
      mod: {Outbox.Application, []}
    ]
  end

  defp deps do
    [
      {:ash, "~> 3.31"}
    ]
  end
end
EOF

RUN cat > /home/user/outbox/mix.lock <<'EOF'
%{
  "ash": {:hex, :ash, "3.31.0", "9ccd7d5ff00a5329a33786063e4a3040681b61d736730cd7aa3f24e5843c1d4f", [:mix], [{:crux, ">= 0.1.2 and < 1.0.0-0", [hex: :crux, repo: "hexpm", optional: false]}, {:decimal, "~> 2.0 or ~> 3.0", [hex: :decimal, repo: "hexpm", optional: false]}, {:ecto, "~> 3.14", [hex: :ecto, repo: "hexpm", optional: false]}, {:ets, "~> 0.8", [hex: :ets, repo: "hexpm", optional: false]}, {:igniter, ">= 0.6.29 and < 1.0.0-0", [hex: :igniter, repo: "hexpm", optional: true]}, {:jason, ">= 1.0.0", [hex: :jason, repo: "hexpm", optional: false]}, {:picosat_elixir, "~> 0.2", [hex: :picosat_elixir, repo: "hexpm", optional: true]}, {:plug, ">= 0.0.0", [hex: :plug, repo: "hexpm", optional: true]}, {:reactor, "~> 1.0", [hex: :reactor, repo: "hexpm", optional: false]}, {:simple_sat, ">= 0.1.1 and < 1.0.0-0", [hex: :simple_sat, repo: "hexpm", optional: true]}, {:spark, ">= 2.6.0", [hex: :spark, repo: "hexpm", optional: false]}, {:splode, "~> 0.3", [hex: :splode, repo: "hexpm", optional: false]}, {:stream_data, "~> 1.0", [hex: :stream_data, repo: "hexpm", optional: false]}, {:telemetry, "~> 1.1", [hex: :telemetry, repo: "hexpm", optional: false]}], "hexpm", "7518ecf694e1b423478ddaa5baf713e9d38448df6873f3be6316f758bc6ab68d"},
  "crux": {:hex, :crux, "0.1.4", "1fa21f5ca886d3498f83871a3ef19379b80abf8cfcf2ed32007e80279e714f1e", [:mix], [{:picosat_elixir, "~> 0.2", [hex: :picosat_elixir, repo: "hexpm", optional: true]}, {:simple_sat, ">= 0.1.1 and < 1.0.0-0", [hex: :simple_sat, repo: "hexpm", optional: true]}, {:stream_data, "~> 1.0", [hex: :stream_data, repo: "hexpm", optional: true]}], "hexpm", "ff7d880cf732d82360aa81e439b8d4831cd30768061c9233f90c97e10162b9c0"},
  "decimal": {:hex, :decimal, "3.1.1", "430d87b04011ce6cbd4fd205be758311a81f87d552d40904abd00f015935b1d0", [:mix], [], "hexpm", "c5f25f2ced74a0587d03e6023f595db8e924c9d3922c8c8ffd9edfc4498cf1f6"},
  "ecto": {:hex, :ecto, "3.14.1", "7b740d87bdf45996aa0c2c2e081640906f10caa7ce5ba328fd294c7d49d0cc6f", [:mix], [{:decimal, "~> 3.0", [hex: :decimal, repo: "hexpm", optional: false]}, {:jason, "~> 1.0", [hex: :jason, repo: "hexpm", optional: true]}, {:telemetry, "~> 0.4 or ~> 1.0", [hex: :telemetry, repo: "hexpm", optional: false]}], "hexpm", "24b991956796700f467d0a3ef3d303138a3ef9ddddf8b98f43758ee067b20a30"},
  "ets": {:hex, :ets, "0.9.0", "79c6a6c205436780486f72d84230c6cba2f8a9920456750ddd1e47389107d5fd", [:mix], [], "hexpm", "2861fdfb04bcaeff370f1a5904eec864f0a56dcfebe5921ea9aadf2a481c822b"},
  "iterex": {:hex, :iterex, "0.1.2", "58f9b9b9a22a55cbfc7b5234a9c9c63eaac26d276b3db80936c0e1c60355a5a6", [:mix], [], "hexpm", "2e103b8bcc81757a9af121f6dc0df312c9a17220f302b1193ef720460d03029d"},
  "jason": {:hex, :jason, "1.4.5", "2e3a008590b0b8d7388c20293e9dcc9cf3e5d642fd2a114e4cbbb52e595d940a", [:mix], [{:decimal, "~> 1.0 or ~> 2.0 or ~> 3.0", [hex: :decimal, repo: "hexpm", optional: true]}], "hexpm", "b0c823996102bcd0239b3c2444eb00409b72f6a140c1950bc8b457d836b30684"},
  "multigraph": {:hex, :multigraph, "0.16.1-mg.4", "2bbe149f5411b0e3bf0624c7bf2e3da2738efeac2f9a67bbbcb807ab171f0a76", [:mix], [], "hexpm", "b9f3e2577cef4658eeedf97c76d22a86d33a7aab702a93c1da9c122e849e9037"},
  "reactor": {:hex, :reactor, "1.0.4", "e19b3bc00776935282e5e0fc1b0dcb87682ec6f3c238ce3150fe7f50bbde502a", [:mix], [{:igniter, "~> 0.4", [hex: :igniter, repo: "hexpm", optional: true]}, {:iterex, "~> 0.1", [hex: :iterex, repo: "hexpm", optional: false]}, {:jason, "~> 1.0", [hex: :jason, repo: "hexpm", optional: false]}, {:multigraph, "~> 0.16.1-mg.2", [hex: :multigraph, repo: "hexpm", optional: false]}, {:spark, ">= 2.3.3 and < 3.0.0-0", [hex: :spark, repo: "hexpm", optional: false]}, {:splode, "~> 0.2", [hex: :splode, repo: "hexpm", optional: false]}, {:telemetry, "~> 1.2", [hex: :telemetry, repo: "hexpm", optional: false]}, {:yaml_elixir, "~> 2.11", [hex: :yaml_elixir, repo: "hexpm", optional: false]}, {:ymlr, "~> 5.0", [hex: :ymlr, repo: "hexpm", optional: false]}], "hexpm", "ba5ec7c9ddc7781f65b6e9818456c4c6b4e997a9a926d83b6f3f12192ef5b395"},
  "spark": {:hex, :spark, "2.7.2", "36becc6ff03b40908cc821d403d7f06d893498e293d2f718afc6ca097fcb9d93", [:mix], [{:igniter, ">= 0.3.64 and < 1.0.0-0", [hex: :igniter, repo: "hexpm", optional: true]}, {:jason, "~> 1.4", [hex: :jason, repo: "hexpm", optional: true]}, {:sourceror, "~> 1.2", [hex: :sourceror, repo: "hexpm", optional: true]}], "hexpm", "adb323ddbf9dbbe326f9e5def54ac96c47911e852b2c270bb19a5147c56f1b45"},
  "splode": {:hex, :splode, "0.3.2", "7716b6b2260a98a6f018c65cc0393da2cdf17314202eb351a0956e8762190dff", [:mix], [], "hexpm", "08fd658f80da7f1cd254b149164dcff8acd44b22f032001d5416b97223d32bc9"},
  "stream_data": {:hex, :stream_data, "1.4.0", "026f929db613aabea6208012ae9b8970d3fd5f88b3bdf26831bc536f98c42036", [:mix], [], "hexpm", "2b0ee3a340dcce1c8cf6302a763ee757d1e01c54d6e16d9069062509d68b1dc9"},
  "telemetry": {:hex, :telemetry, "1.4.2", "a0cb522801dffb1c49fe6e30561badffc7b6d0e180db1300df759faa22062855", [:rebar3], [], "hexpm", "928f6495066506077862c0d1646609eed891a4326bee3126ba54b60af61febb1"},
  "yamerl": {:hex, :yamerl, "0.10.0", "4ff81fee2f1f6a46f1700c0d880b24d193ddb74bd14ef42cb0bcf46e81ef2f8e", [:rebar3], [], "hexpm", "346adb2963f1051dc837a2364e4acf6eb7d80097c0f53cbdc3046ec8ec4b4e6e"},
  "yaml_elixir": {:hex, :yaml_elixir, "2.12.2", "9dd1330fb4cd9a36a7b0f502e5b12486eff632792ee4a5f0eba52a4d4ec32c9c", [:mix], [{:yamerl, "~> 0.10", [hex: :yamerl, repo: "hexpm", optional: false]}], "hexpm", "e7c1b10122f973e6558462d51c39026ba0e14afbc6745318e990ea82cfe9e159"},
  "ymlr": {:hex, :ymlr, "5.1.6", "247479328fd5ea1e222ee59ecd5571ab2885cf1a6329aea458d4944cd035cfc1", [:mix], [], "hexpm", "b36d7c72384d2cb2094d2a3c8b0c3b12303e0ccd1b7b12333b81d75b1fe0b53a"},
}
EOF

RUN cat > /home/user/outbox/.formatter.exs <<'EOF'
[
  import_deps: [:ash],
  inputs: ["{mix,.formatter}.exs", "{config,lib,test}/**/*.{ex,exs}"]
]
EOF

RUN cat > /home/user/outbox/config/config.exs <<'EOF'
import Config

config :outbox, ash_domains: [Outbox.Ledger]

config :logger, level: :warning
EOF

RUN cat > /home/user/outbox/lib/outbox/application.ex <<'EOF'
defmodule Outbox.Application do
  @moduledoc false

  use Application

  @impl true
  def start(_type, _args) do
    children = []

    Supervisor.start_link(children, strategy: :one_for_one, name: Outbox.Supervisor)
  end
end
EOF

RUN cat > /home/user/outbox/lib/outbox/ledger.ex <<'EOF'
defmodule Outbox.Ledger do
  @moduledoc """
  The ledger domain: accounts and transfers, stored in memory.
  """

  use Ash.Domain, otp_app: :outbox

  resources do
    resource Outbox.Ledger.Account
    resource Outbox.Ledger.Transfer
  end
end
EOF

RUN cat > /home/user/outbox/lib/outbox/ledger/account.ex <<'EOF'
defmodule Outbox.Ledger.Account do
  @moduledoc """
  A ledger account.
  """

  use Ash.Resource,
    otp_app: :outbox,
    domain: Outbox.Ledger,
    data_layer: Ash.DataLayer.Ets

  ets do
    private? false
  end

  attributes do
    uuid_primary_key :id

    attribute :owner_id, :string, allow_nil?: false, public?: true
    attribute :name, :string, allow_nil?: false, public?: true
    attribute :balance, :integer, allow_nil?: false, default: 0, public?: true

    attribute :status, :atom,
      allow_nil?: false,
      default: :active,
      constraints: [one_of: [:active, :frozen, :closed]],
      public?: true
  end

  actions do
    defaults [:read]

    create :open do
      primary? true
      accept [:owner_id, :name, :balance]
    end

    update :rename do
      accept [:name]
    end

    update :freeze do
      accept []
      change set_attribute(:status, :frozen)
    end

    update :deposit do
      accept []
      argument :amount, :integer, allow_nil?: false
      change atomic_update(:balance, expr(balance + ^arg(:amount)))
    end

    update :withdraw do
      require_atomic? false
      accept []
      argument :amount, :integer, allow_nil?: false
      validate {Outbox.Ledger.SufficientFunds, []}
      change atomic_update(:balance, expr(balance - ^arg(:amount)))
    end

    destroy :close do
      primary? true
    end
  end
end
EOF

RUN cat > /home/user/outbox/lib/outbox/ledger/transfer.ex <<'EOF'
defmodule Outbox.Ledger.Transfer do
  @moduledoc """
  A transfer between two ledger accounts.
  """

  use Ash.Resource,
    otp_app: :outbox,
    domain: Outbox.Ledger,
    data_layer: Ash.DataLayer.Ets

  ets do
    private? false
  end

  attributes do
    uuid_primary_key :id

    attribute :from_account_id, :string, allow_nil?: false, public?: true
    attribute :to_account_id, :string, allow_nil?: false, public?: true
    attribute :amount, :integer, allow_nil?: false, public?: true

    attribute :state, :atom,
      allow_nil?: false,
      default: :pending,
      constraints: [one_of: [:pending, :settled]],
      public?: true
  end

  actions do
    defaults [:read, :destroy]

    create :record do
      primary? true
      accept [:from_account_id, :to_account_id, :amount]
    end

    update :settle do
      accept []
      change set_attribute(:state, :settled)
    end
  end
end
EOF

RUN cat > /home/user/outbox/lib/outbox/ledger/sufficient_funds.ex <<'EOF'
defmodule Outbox.Ledger.SufficientFunds do
  @moduledoc """
  Rejects a withdrawal that is not positive or that would overdraw the account.
  """

  use Ash.Resource.Validation

  @impl true
  def validate(changeset, _opts, _context) do
    amount = Ash.Changeset.get_argument(changeset, :amount)

    cond do
      not is_integer(amount) or amount <= 0 ->
        {:error,
         Ash.Error.Changes.InvalidArgument.exception(
           field: :amount,
           message: "must be positive"
         )}

      amount > changeset.data.balance ->
        {:error,
         Ash.Error.Changes.InvalidArgument.exception(
           field: :amount,
           message: "insufficient funds"
         )}

      true ->
        :ok
    end
  end
end
EOF

# Vendor and pre-compile every dependency for both MIX_ENVs so the image works offline.
RUN cd /home/user/outbox && \
    mix deps.get && \
    mix deps.compile && \
    mix compile && \
    MIX_ENV=test mix deps.compile && \
    MIX_ENV=test mix compile && \
    chmod -R a+rwX /home/user/outbox /opt/mix /opt/hex

ENV HEX_OFFLINE=1
ENV MIX_ENV=dev

LABEL Author="generate-harbor-tasks"
LABEL Description="Offline Elixir/OTP + Ash Framework 3.31 environment with a scaffolded in-memory ledger project at /home/user/outbox."

CMD ["/bin/bash", "-c", "trap : TERM INT; sleep infinity & wait"]

# Container contents:
#   - always required apt packages: curl wget ca-certificates git python3 python3-pip python3-pytest bash ripgrep
#   - always required pip3 packages: pytest-json-ctrf
#   - Erlang/OTP 27.3.4 and Elixir 1.18.4 installed from builds.hex.pm into /opt/otp and /opt/elixir
#   - Hex/Mix caches in /opt/hex and /opt/mix, world writable, with HEX_OFFLINE=1 for offline solving
#   - /home/user/outbox: Ash Framework 3.31 mix project (ledger domain on the ETS data layer)
#   - /home/user/outbox/deps + /home/user/outbox/_build: vendored and pre-compiled for dev and test

COPY test_initial_state.py /bootstrap/test_initial_state.py

# Setup entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
