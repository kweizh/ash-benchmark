FROM ubuntu:24.04

ARG POCHI_VERSION
ARG OTP_VERSION=27.3.4
ARG ELIXIR_VERSION=1.18.4

ENV LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    MIX_HOME=/opt/mix \
    HEX_HOME=/opt/hex \
    PATH=/opt/otp/bin:/opt/elixir/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

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

# Pinned Erlang/OTP + Elixir builds from builds.hex.pm (arch aware, works on amd64 and arm64).
RUN mkdir -p /opt/otp && \
    curl -fsSL "https://builds.hex.pm/builds/otp/$(dpkg --print-architecture)/ubuntu-24.04/OTP-${OTP_VERSION}.tar.gz" -o /tmp/otp.tar.gz && \
    tar -xzf /tmp/otp.tar.gz -C /opt/otp --strip-components=1 && \
    rm /tmp/otp.tar.gz && \
    cd /opt/otp && \
    ./Install -minimal /opt/otp

RUN mkdir -p /opt/elixir && \
    curl -fsSL "https://builds.hex.pm/builds/elixir/v${ELIXIR_VERSION}-otp-27.zip" -o /tmp/elixir.zip && \
    unzip -q /tmp/elixir.zip -d /opt/elixir && \
    rm /tmp/elixir.zip

RUN mkdir -p /opt/mix /opt/hex && \
    mix local.hex --force && \
    mix local.rebar --force && \
    chmod -R a+rX /opt/mix /opt/hex

RUN mkdir -p /home/user && chmod 0755 /home/user

WORKDIR /home/user/thread_graph

RUN mkdir -p config lib/thread_graph/forum && \
    cat > mix.exs <<'MIXEOF'
defmodule ThreadGraph.MixProject do
  use Mix.Project

  def project do
    [
      app: :thread_graph,
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
      {:ash, "~> 3.31"},
      {:jason, "~> 1.4"}
    ]
  end
end
MIXEOF

RUN cat > mix.lock <<'LOCKEOF'
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
LOCKEOF

# Fetch and compile every dependency for both MIX_ENVs so the image works offline.
RUN mix deps.get && \
    MIX_ENV=dev mix deps.compile && \
    MIX_ENV=test mix deps.compile

ENV HEX_OFFLINE=1

RUN cat > .formatter.exs <<'FMTEOF'
[
  import_deps: [:ash],
  inputs: ["{mix,.formatter}.exs", "{config,lib,test}/**/*.{ex,exs}"]
]
FMTEOF

RUN cat > config/config.exs <<'CFGEOF'
import Config

config :thread_graph, ash_domains: [ThreadGraph.Forum]

config :logger, level: :warning
CFGEOF

RUN cat > lib/thread_graph/forum.ex <<'DOMEOF'
defmodule ThreadGraph.Forum do
  @moduledoc """
  The discussion-board domain.
  """
  use Ash.Domain, otp_app: :thread_graph

  resources do
    resource ThreadGraph.Forum.Author
    resource ThreadGraph.Forum.Thread
    resource ThreadGraph.Forum.Message
    resource ThreadGraph.Forum.MessageLink
  end
end
DOMEOF

RUN cat > lib/thread_graph/forum/load_counter.ex <<'LCEOF'
defmodule ThreadGraph.Forum.LoadCounter do
  @moduledoc """
  A tiny global invocation counter.

  It is deliberately process independent so that a counter bumped inside a data
  loading callback can be observed from anywhere in the VM.

  DO NOT MODIFY THIS MODULE.
  """

  @key {__MODULE__, :counts}

  @doc "Clears every counter."
  @spec reset() :: :ok
  def reset do
    :persistent_term.put(@key, %{})
    :ok
  end

  @doc "Increments the counter stored under `key`."
  @spec bump(atom()) :: :ok
  def bump(key) when is_atom(key) do
    counts = :persistent_term.get(@key, %{})
    :persistent_term.put(@key, Map.update(counts, key, 1, &(&1 + 1)))
    :ok
  end

  @doc "Returns the current value of the counter stored under `key`."
  @spec count(atom()) :: non_neg_integer()
  def count(key) when is_atom(key), do: Map.get(counts(), key, 0)

  @doc "Returns every counter as a map."
  @spec counts() :: %{optional(atom()) => non_neg_integer()}
  def counts, do: :persistent_term.get(@key, %{})
end
LCEOF

RUN cat > lib/thread_graph/forum/author.ex <<'AUTEOF'
defmodule ThreadGraph.Forum.Author do
  @moduledoc "Somebody who posts messages."
  use Ash.Resource,
    otp_app: :thread_graph,
    domain: ThreadGraph.Forum,
    data_layer: Ash.DataLayer.Ets

  attributes do
    uuid_primary_key :id

    attribute :handle, :string, allow_nil?: false, public?: true
    attribute :display_name, :string, public?: true
  end

  actions do
    defaults [
      :read,
      :destroy,
      create: [:handle, :display_name],
      update: [:handle, :display_name]
    ]
  end

  relationships do
    has_many :messages, ThreadGraph.Forum.Message do
      public? true
    end
  end
end
AUTEOF

RUN cat > lib/thread_graph/forum/thread.ex <<'THREOF'
defmodule ThreadGraph.Forum.Thread do
  @moduledoc "A discussion thread on a board."
  use Ash.Resource,
    otp_app: :thread_graph,
    domain: ThreadGraph.Forum,
    data_layer: Ash.DataLayer.Ets

  attributes do
    uuid_primary_key :id

    attribute :slug, :string, allow_nil?: false, public?: true
    attribute :title, :string, allow_nil?: false, public?: true
    attribute :board, :string, allow_nil?: false, public?: true
    attribute :locked, :boolean, allow_nil?: false, default: false, public?: true
  end

  actions do
    defaults [
      :read,
      :destroy,
      create: [:slug, :title, :board, :locked],
      update: [:title, :locked]
    ]
  end

  relationships do
    has_many :messages, ThreadGraph.Forum.Message do
      public? true
    end
  end
end
THREOF

RUN cat > lib/thread_graph/forum/message.ex <<'MSGEOF'
defmodule ThreadGraph.Forum.Message do
  @moduledoc "A single message inside a thread."
  use Ash.Resource,
    otp_app: :thread_graph,
    domain: ThreadGraph.Forum,
    data_layer: Ash.DataLayer.Ets

  attributes do
    uuid_primary_key :id

    attribute :body, :string, allow_nil?: false, public?: true
    attribute :position, :integer, allow_nil?: false, public?: true
    attribute :score, :integer, allow_nil?: false, default: 0, public?: true
  end

  actions do
    defaults [
      :read,
      :destroy,
      create: [:body, :position, :score, :thread_id, :author_id, :parent_id],
      update: [:body, :position, :score, :parent_id]
    ]
  end

  relationships do
    belongs_to :thread, ThreadGraph.Forum.Thread do
      allow_nil? false
      attribute_writable? true
      public? true
    end

    belongs_to :author, ThreadGraph.Forum.Author do
      attribute_writable? true
      public? true
    end

    belongs_to :parent, ThreadGraph.Forum.Message do
      source_attribute :parent_id
      attribute_writable? true
      public? true
    end

    has_many :replies, ThreadGraph.Forum.Message do
      destination_attribute :parent_id
      public? true
    end
  end
end
MSGEOF

RUN cat > lib/thread_graph/forum/message_link.ex <<'LNKEOF'
defmodule ThreadGraph.Forum.MessageLink do
  @moduledoc "A directed edge between two messages."
  use Ash.Resource,
    otp_app: :thread_graph,
    domain: ThreadGraph.Forum,
    data_layer: Ash.DataLayer.Ets

  attributes do
    uuid_primary_key :id

    attribute :kind, :atom,
      allow_nil?: false,
      public?: true,
      constraints: [one_of: [:follow_up, :duplicate_of, :fork_of]]
  end

  actions do
    defaults [
      :read,
      :destroy,
      create: [:kind, :from_message_id, :to_message_id]
    ]
  end

  relationships do
    belongs_to :from_message, ThreadGraph.Forum.Message do
      allow_nil? false
      attribute_writable? true
      public? true
    end

    belongs_to :to_message, ThreadGraph.Forum.Message do
      allow_nil? false
      attribute_writable? true
      public? true
    end
  end
end
LNKEOF

RUN MIX_ENV=dev mix compile && \
    MIX_ENV=test mix compile && \
    chmod -R a+rwX /home/user

WORKDIR /home/user

LABEL Author="generate-harbor-tasks"
LABEL Description="Offline Elixir 1.18.4 / OTP 27.3.4 image with a pre-compiled Ash Framework 3.31 discussion-board scaffold at /home/user/thread_graph."

CMD ["/bin/bash", "-c", "trap : TERM INT; sleep infinity & wait"]

# Container contents:
#   - always required apt packages: curl wget ca-certificates git python3 python3-pip python3-pytest bash ripgrep
#   - always required pip3 packages: pytest-json-ctrf
#   - Erlang/OTP 27.3.4 and Elixir 1.18.4 installed from builds.hex.pm into /opt/otp and /opt/elixir
#   - MIX_HOME=/opt/mix, HEX_HOME=/opt/hex and HEX_OFFLINE=1 so mix never needs the network
#   - /home/user/thread_graph: Ash Framework v3 project (ash 3.31, Ash.DataLayer.Ets), deps fetched,
#     mix.lock committed and every dependency pre-compiled for MIX_ENV=dev and MIX_ENV=test
#   - /home/user/thread_graph/lib/thread_graph/forum: ThreadGraph.Forum domain plus the Author,
#     Thread, Message and MessageLink resources and the ThreadGraph.Forum.LoadCounter helper

COPY test_initial_state.py /bootstrap/test_initial_state.py

# Setup entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
