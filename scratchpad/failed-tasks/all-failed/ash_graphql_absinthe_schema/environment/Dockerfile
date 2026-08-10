FROM ubuntu:24.04

ARG POCHI_VERSION
ARG OTP_VERSION=27.3.4
ARG ELIXIR_VERSION=1.18.4

ENV LANG=C.UTF-8

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

# Pinned Erlang/OTP + Elixir, downloaded as prebuilt archives (arch aware).
RUN arch="$(dpkg --print-architecture)" && \
    curl -fsSL --retry 8 --retry-delay 5 --retry-all-errors \
        -o /tmp/otp.tar.gz \
        "https://builds.hex.pm/builds/otp/${arch}/ubuntu-24.04/OTP-${OTP_VERSION}.tar.gz" && \
    mkdir -p /opt/otp && \
    tar -xzf /tmp/otp.tar.gz -C /opt/otp --strip-components=1 && \
    cd /opt/otp && ./Install -minimal /opt/otp && \
    rm -f /tmp/otp.tar.gz && \
    curl -fsSL --retry 8 --retry-delay 5 --retry-all-errors \
        -o /tmp/elixir.zip \
        "https://builds.hex.pm/builds/elixir/v${ELIXIR_VERSION}-otp-27.zip" && \
    mkdir -p /opt/elixir && \
    unzip -q /tmp/elixir.zip -d /opt/elixir && \
    rm -f /tmp/elixir.zip

ENV PATH="/opt/otp/bin:/opt/elixir/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
ENV MIX_HOME=/opt/mix
ENV HEX_HOME=/opt/hex

RUN mkdir -p /opt/mix /opt/hex && \
    (for i in 1 2 3 4 5 6; do mix local.hex --force && break; sleep 10; done) && \
    (for i in 1 2 3 4 5 6; do mix local.rebar --force && break; sleep 10; done) && \
    chmod -R a+rX /opt/mix /opt/hex

RUN mkdir -p /home/user && chmod 0755 /home/user

RUN mkdir -p /home/user/tracker/config \
             /home/user/tracker/lib/tracker/delivery/errors

RUN cat > /home/user/tracker/mix.exs <<'HARBOR_EOF'
defmodule Tracker.MixProject do
  use Mix.Project

  def project do
    [
      app: :tracker,
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
      mod: {Tracker.Application, []}
    ]
  end

  defp deps do
    [
      {:ash, "~> 3.31"},
      {:ash_graphql, "~> 1.10"},
      {:simple_sat, "~> 0.1"}
    ]
  end
end
HARBOR_EOF

RUN cat > /home/user/tracker/mix.lock <<'HARBOR_EOF'
%{
  "absinthe": {:hex, :absinthe, "1.11.0", "dee6dfa57f86d52b25d8b0f925585b6b047d4921ac703c1075b6e7b8bc2fc83c", [:mix], [{:dataloader, "~> 1.0.0 or ~> 2.0", [hex: :dataloader, repo: "hexpm", optional: true]}, {:decimal, "~> 2.0 or ~> 3.0", [hex: :decimal, repo: "hexpm", optional: true]}, {:nimble_parsec, "~> 1.2.2 or ~> 1.3", [hex: :nimble_parsec, repo: "hexpm", optional: false]}, {:opentelemetry_process_propagator, "~> 0.2.1 or ~> 0.3", [hex: :opentelemetry_process_propagator, repo: "hexpm", optional: true]}, {:telemetry, "~> 0.4 or ~> 1.0", [hex: :telemetry, repo: "hexpm", optional: false]}], "hexpm", "39b3b4b6e3eb405fa98b449feef0dacff81d89bf01c2866cfa513616c5530ba6"},
  "absinthe_plug": {:hex, :absinthe_plug, "1.5.10", "c9e207235aaa8a086a5db6801a9bebaea035f7b5a2703cb98d962646ef70c76f", [:mix], [{:absinthe, "~> 1.7", [hex: :absinthe, repo: "hexpm", optional: false]}, {:plug, "~> 1.4", [hex: :plug, repo: "hexpm", optional: false]}], "hexpm", "489ac1951c8e4128571141c60a0669a720619bc161f801a8c6be8cfaf7ab0979"},
  "ash": {:hex, :ash, "3.31.0", "9ccd7d5ff00a5329a33786063e4a3040681b61d736730cd7aa3f24e5843c1d4f", [:mix], [{:crux, ">= 0.1.2 and < 1.0.0-0", [hex: :crux, repo: "hexpm", optional: false]}, {:decimal, "~> 2.0 or ~> 3.0", [hex: :decimal, repo: "hexpm", optional: false]}, {:ecto, "~> 3.14", [hex: :ecto, repo: "hexpm", optional: false]}, {:ets, "~> 0.8", [hex: :ets, repo: "hexpm", optional: false]}, {:igniter, ">= 0.6.29 and < 1.0.0-0", [hex: :igniter, repo: "hexpm", optional: true]}, {:jason, ">= 1.0.0", [hex: :jason, repo: "hexpm", optional: false]}, {:picosat_elixir, "~> 0.2", [hex: :picosat_elixir, repo: "hexpm", optional: true]}, {:plug, ">= 0.0.0", [hex: :plug, repo: "hexpm", optional: true]}, {:reactor, "~> 1.0", [hex: :reactor, repo: "hexpm", optional: false]}, {:simple_sat, ">= 0.1.1 and < 1.0.0-0", [hex: :simple_sat, repo: "hexpm", optional: true]}, {:spark, ">= 2.6.0", [hex: :spark, repo: "hexpm", optional: false]}, {:splode, "~> 0.3", [hex: :splode, repo: "hexpm", optional: false]}, {:stream_data, "~> 1.0", [hex: :stream_data, repo: "hexpm", optional: false]}, {:telemetry, "~> 1.1", [hex: :telemetry, repo: "hexpm", optional: false]}], "hexpm", "7518ecf694e1b423478ddaa5baf713e9d38448df6873f3be6316f758bc6ab68d"},
  "ash_graphql": {:hex, :ash_graphql, "1.10.0", "bf3c0c2b329b2118e519defcaf797e90187ddb44604e45dba927ab7eba87e685", [:mix], [{:absinthe, "~> 1.7", [hex: :absinthe, repo: "hexpm", optional: false]}, {:absinthe_phoenix, "~> 2.0", [hex: :absinthe_phoenix, repo: "hexpm", optional: true]}, {:absinthe_plug, "~> 1.4", [hex: :absinthe_plug, repo: "hexpm", optional: false]}, {:ash, ">= 3.5.13 and < 4.0.0-0", [hex: :ash, repo: "hexpm", optional: false]}, {:igniter, ">= 0.5.28 and < 1.0.0-0", [hex: :igniter, repo: "hexpm", optional: true]}, {:jason, "~> 1.2", [hex: :jason, repo: "hexpm", optional: false]}, {:spark, ">= 2.2.10", [hex: :spark, repo: "hexpm", optional: false]}], "hexpm", "9dbd9613e53dcc9f9b19686f12d751f3433cb5beb52b56d77577a0bc7dd23c91"},
  "crux": {:hex, :crux, "0.1.4", "1fa21f5ca886d3498f83871a3ef19379b80abf8cfcf2ed32007e80279e714f1e", [:mix], [{:picosat_elixir, "~> 0.2", [hex: :picosat_elixir, repo: "hexpm", optional: true]}, {:simple_sat, ">= 0.1.1 and < 1.0.0-0", [hex: :simple_sat, repo: "hexpm", optional: true]}, {:stream_data, "~> 1.0", [hex: :stream_data, repo: "hexpm", optional: true]}], "hexpm", "ff7d880cf732d82360aa81e439b8d4831cd30768061c9233f90c97e10162b9c0"},
  "decimal": {:hex, :decimal, "3.1.1", "430d87b04011ce6cbd4fd205be758311a81f87d552d40904abd00f015935b1d0", [:mix], [], "hexpm", "c5f25f2ced74a0587d03e6023f595db8e924c9d3922c8c8ffd9edfc4498cf1f6"},
  "ecto": {:hex, :ecto, "3.14.1", "7b740d87bdf45996aa0c2c2e081640906f10caa7ce5ba328fd294c7d49d0cc6f", [:mix], [{:decimal, "~> 3.0", [hex: :decimal, repo: "hexpm", optional: false]}, {:jason, "~> 1.0", [hex: :jason, repo: "hexpm", optional: true]}, {:telemetry, "~> 0.4 or ~> 1.0", [hex: :telemetry, repo: "hexpm", optional: false]}], "hexpm", "24b991956796700f467d0a3ef3d303138a3ef9ddddf8b98f43758ee067b20a30"},
  "ets": {:hex, :ets, "0.9.0", "79c6a6c205436780486f72d84230c6cba2f8a9920456750ddd1e47389107d5fd", [:mix], [], "hexpm", "2861fdfb04bcaeff370f1a5904eec864f0a56dcfebe5921ea9aadf2a481c822b"},
  "iterex": {:hex, :iterex, "0.1.2", "58f9b9b9a22a55cbfc7b5234a9c9c63eaac26d276b3db80936c0e1c60355a5a6", [:mix], [], "hexpm", "2e103b8bcc81757a9af121f6dc0df312c9a17220f302b1193ef720460d03029d"},
  "jason": {:hex, :jason, "1.4.5", "2e3a008590b0b8d7388c20293e9dcc9cf3e5d642fd2a114e4cbbb52e595d940a", [:mix], [{:decimal, "~> 1.0 or ~> 2.0 or ~> 3.0", [hex: :decimal, repo: "hexpm", optional: true]}], "hexpm", "b0c823996102bcd0239b3c2444eb00409b72f6a140c1950bc8b457d836b30684"},
  "mime": {:hex, :mime, "2.0.7", "b8d739037be7cd402aee1ba0306edfdef982687ee7e9859bee6198c1e7e2f128", [:mix], [], "hexpm", "6171188e399ee16023ffc5b76ce445eb6d9672e2e241d2df6050f3c771e80ccd"},
  "multigraph": {:hex, :multigraph, "0.16.1-mg.4", "2bbe149f5411b0e3bf0624c7bf2e3da2738efeac2f9a67bbbcb807ab171f0a76", [:mix], [], "hexpm", "b9f3e2577cef4658eeedf97c76d22a86d33a7aab702a93c1da9c122e849e9037"},
  "nimble_parsec": {:hex, :nimble_parsec, "1.4.2", "8efba0122db06df95bfaa78f791344a89352ba04baedd3849593bfce4d0dc1c6", [:mix], [], "hexpm", "4b21398942dda052b403bbe1da991ccd03a053668d147d53fb8c4e0efe09c973"},
  "plug": {:hex, :plug, "1.20.3", "56c480c633ec2ce10140e236e15233bf576e1d323887d7c96711bd02ab5160db", [:mix], [{:mime, "~> 1.0 or ~> 2.0", [hex: :mime, repo: "hexpm", optional: false]}, {:plug_crypto, "~> 1.1.1 or ~> 1.2 or ~> 2.0", [hex: :plug_crypto, repo: "hexpm", optional: false]}, {:telemetry, "~> 0.4.3 or ~> 1.0", [hex: :telemetry, repo: "hexpm", optional: false]}], "hexpm", "be266aee1b8536ef6409d58cf39a3121319f0ec47cfa1b24024485aa0e76ad76"},
  "plug_crypto": {:hex, :plug_crypto, "2.2.0", "144014737daaf485407f5ed77daeaad74d651b216a28c87543f8cc7043f8efc8", [:mix], [], "hexpm", "83a95744ab1c75876542b6fab135fcc176280e0f301a111c1f757fddcec95d2c"},
  "reactor": {:hex, :reactor, "1.0.5", "43a3298fb5874248e72d61662704d5013194c427afcf740e14336f3379f53ed3", [:mix], [{:igniter, "~> 0.4", [hex: :igniter, repo: "hexpm", optional: true]}, {:iterex, "~> 0.1", [hex: :iterex, repo: "hexpm", optional: false]}, {:jason, "~> 1.0", [hex: :jason, repo: "hexpm", optional: false]}, {:multigraph, "~> 0.16.1-mg.2", [hex: :multigraph, repo: "hexpm", optional: false]}, {:spark, ">= 2.3.3 and < 3.0.0-0", [hex: :spark, repo: "hexpm", optional: false]}, {:splode, "~> 0.2", [hex: :splode, repo: "hexpm", optional: false]}, {:telemetry, "~> 1.2", [hex: :telemetry, repo: "hexpm", optional: false]}, {:yaml_elixir, "~> 2.11", [hex: :yaml_elixir, repo: "hexpm", optional: false]}, {:ymlr, "~> 5.0", [hex: :ymlr, repo: "hexpm", optional: false]}], "hexpm", "8867decb795d0b87a9dea5d146721af60312c0b45443d125d9be535946e8da19"},
  "simple_sat": {:hex, :simple_sat, "0.1.4", "39baf72cdca14f93c0b6ce2b6418b72bbb67da98fa9ca4384e2f79bbc299899d", [:mix], [], "hexpm", "3569b68e346a5fd7154b8d14173ff8bcc829f2eb7b088c30c3f42a383443930b"},
  "spark": {:hex, :spark, "2.7.2", "36becc6ff03b40908cc821d403d7f06d893498e293d2f718afc6ca097fcb9d93", [:mix], [{:igniter, ">= 0.3.64 and < 1.0.0-0", [hex: :igniter, repo: "hexpm", optional: true]}, {:jason, "~> 1.4", [hex: :jason, repo: "hexpm", optional: true]}, {:sourceror, "~> 1.2", [hex: :sourceror, repo: "hexpm", optional: true]}], "hexpm", "adb323ddbf9dbbe326f9e5def54ac96c47911e852b2c270bb19a5147c56f1b45"},
  "splode": {:hex, :splode, "0.3.2", "7716b6b2260a98a6f018c65cc0393da2cdf17314202eb351a0956e8762190dff", [:mix], [], "hexpm", "08fd658f80da7f1cd254b149164dcff8acd44b22f032001d5416b97223d32bc9"},
  "stream_data": {:hex, :stream_data, "1.4.0", "026f929db613aabea6208012ae9b8970d3fd5f88b3bdf26831bc536f98c42036", [:mix], [], "hexpm", "2b0ee3a340dcce1c8cf6302a763ee757d1e01c54d6e16d9069062509d68b1dc9"},
  "telemetry": {:hex, :telemetry, "1.4.2", "a0cb522801dffb1c49fe6e30561badffc7b6d0e180db1300df759faa22062855", [:rebar3], [], "hexpm", "928f6495066506077862c0d1646609eed891a4326bee3126ba54b60af61febb1"},
  "yamerl": {:hex, :yamerl, "0.10.0", "4ff81fee2f1f6a46f1700c0d880b24d193ddb74bd14ef42cb0bcf46e81ef2f8e", [:rebar3], [], "hexpm", "346adb2963f1051dc837a2364e4acf6eb7d80097c0f53cbdc3046ec8ec4b4e6e"},
  "yaml_elixir": {:hex, :yaml_elixir, "2.12.2", "9dd1330fb4cd9a36a7b0f502e5b12486eff632792ee4a5f0eba52a4d4ec32c9c", [:mix], [{:yamerl, "~> 0.10", [hex: :yamerl, repo: "hexpm", optional: false]}], "hexpm", "e7c1b10122f973e6558462d51c39026ba0e14afbc6745318e990ea82cfe9e159"},
  "ymlr": {:hex, :ymlr, "5.1.6", "247479328fd5ea1e222ee59ecd5571ab2885cf1a6329aea458d4944cd035cfc1", [:mix], [], "hexpm", "b36d7c72384d2cb2094d2a3c8b0c3b12303e0ccd1b7b12333b81d75b1fe0b53a"},
}
HARBOR_EOF

RUN cat > /home/user/tracker/config/config.exs <<'HARBOR_EOF'
import Config

config :tracker, ash_domains: [Tracker.Delivery]

config :logger, level: :warning

config :ash, :policies, show_policy_breakdowns?: false
HARBOR_EOF

RUN cat > /home/user/tracker/lib/tracker/application.ex <<'HARBOR_EOF'
defmodule Tracker.Application do
  @moduledoc false
  use Application

  @impl true
  def start(_type, _args) do
    Supervisor.start_link([], strategy: :one_for_one, name: Tracker.Supervisor)
  end
end
HARBOR_EOF

RUN cat > /home/user/tracker/lib/tracker/delivery.ex <<'HARBOR_EOF'
defmodule Tracker.Delivery do
  @moduledoc false
  use Ash.Domain, otp_app: :tracker

  resources do
    resource Tracker.Delivery.User
    resource Tracker.Delivery.Project
    resource Tracker.Delivery.Ticket
    resource Tracker.Delivery.Label
    resource Tracker.Delivery.TicketLabel
  end
end
HARBOR_EOF

RUN cat > /home/user/tracker/lib/tracker/delivery/user_role.ex <<'HARBOR_EOF'
defmodule Tracker.Delivery.UserRole do
  @moduledoc false
  use Ash.Type.Enum, values: [:member, :admin]
end
HARBOR_EOF

RUN cat > /home/user/tracker/lib/tracker/delivery/ticket_status.ex <<'HARBOR_EOF'
defmodule Tracker.Delivery.TicketStatus do
  @moduledoc false
  use Ash.Type.Enum, values: [:open, :in_progress, :blocked, :done]
end
HARBOR_EOF

RUN cat > /home/user/tracker/lib/tracker/delivery/errors/sprint_frozen.ex <<'HARBOR_EOF'
defmodule Tracker.Delivery.Errors.SprintFrozen do
  @moduledoc false
  use Splode.Error, fields: [:project_slug], class: :invalid

  def message(%{project_slug: slug}) do
    "sprint #{slug} is already frozen"
  end
end
HARBOR_EOF

RUN cat > /home/user/tracker/lib/tracker/delivery/user.ex <<'HARBOR_EOF'
defmodule Tracker.Delivery.User do
  @moduledoc false
  use Ash.Resource,
    otp_app: :tracker,
    domain: Tracker.Delivery,
    data_layer: Ash.DataLayer.Ets

  ets do
    private? true
  end

  attributes do
    uuid_primary_key :id

    attribute :email, :string, allow_nil?: false, public?: true
    attribute :display_name, :string, allow_nil?: false, public?: true

    attribute :role, Tracker.Delivery.UserRole,
      allow_nil?: false,
      default: :member,
      public?: true

    attribute :internal_notes, :string, public?: true
  end

  actions do
    defaults [:read, :destroy, create: :*, update: :*]
  end

  relationships do
    has_many :assigned_tickets, Tracker.Delivery.Ticket do
      destination_attribute :assignee_id
      public? true
    end
  end
end
HARBOR_EOF

RUN cat > /home/user/tracker/lib/tracker/delivery/label.ex <<'HARBOR_EOF'
defmodule Tracker.Delivery.Label do
  @moduledoc false
  use Ash.Resource,
    otp_app: :tracker,
    domain: Tracker.Delivery,
    data_layer: Ash.DataLayer.Ets

  ets do
    private? true
  end

  attributes do
    uuid_primary_key :id
    attribute :name, :string, allow_nil?: false, public?: true
    attribute :colour, :string, public?: true
  end

  actions do
    defaults [:read, :destroy, create: :*, update: :*]
  end

  relationships do
    many_to_many :tickets, Tracker.Delivery.Ticket do
      through Tracker.Delivery.TicketLabel
      source_attribute_on_join_resource :label_id
      destination_attribute_on_join_resource :ticket_id
      public? true
    end
  end
end
HARBOR_EOF

RUN cat > /home/user/tracker/lib/tracker/delivery/ticket_label.ex <<'HARBOR_EOF'
defmodule Tracker.Delivery.TicketLabel do
  @moduledoc false
  use Ash.Resource,
    otp_app: :tracker,
    domain: Tracker.Delivery,
    data_layer: Ash.DataLayer.Ets

  ets do
    private? true
  end

  attributes do
    uuid_primary_key :id
  end

  actions do
    defaults [:read, :destroy, create: :*, update: :*]
  end

  relationships do
    belongs_to :ticket, Tracker.Delivery.Ticket do
      allow_nil? false
      attribute_writable? true
    end

    belongs_to :label, Tracker.Delivery.Label do
      allow_nil? false
      attribute_writable? true
    end
  end
end
HARBOR_EOF

RUN cat > /home/user/tracker/lib/tracker/delivery/project.ex <<'HARBOR_EOF'
defmodule Tracker.Delivery.Project do
  @moduledoc false
  use Ash.Resource,
    otp_app: :tracker,
    domain: Tracker.Delivery,
    data_layer: Ash.DataLayer.Ets,
    authorizers: [Ash.Policy.Authorizer]

  require Ash.Query

  ets do
    private? true
  end

  attributes do
    uuid_primary_key :id
    attribute :name, :string, allow_nil?: false, public?: true
    attribute :slug, :string, allow_nil?: false, public?: true
    attribute :archived, :boolean, allow_nil?: false, default: false, public?: true
  end

  actions do
    defaults [:read, :destroy]

    create :create do
      primary? true
      accept [:name, :slug]
    end

    update :archive do
      accept []
      change set_attribute(:archived, true)
    end

    action :audit_sprint, :string do
      argument :slug, :string, allow_nil?: false

      run fn input, _context ->
        raise "audit backend offline for #{input.arguments.slug}"
      end
    end

    action :freeze_sprint, :string do
      argument :slug, :string, allow_nil?: false
      argument :reason, :string, allow_nil?: false

      run fn input, _context ->
        slug = input.arguments.slug

        query = Ash.Query.filter(__MODULE__, slug == ^slug)

        case Ash.read_one(query, authorize?: false) do
          {:ok, nil} ->
            {:error, Ash.Error.Query.NotFound.exception(resource: __MODULE__)}

          {:ok, %{archived: true} = project} ->
            {:error, Tracker.Delivery.Errors.SprintFrozen.exception(project_slug: project.slug)}

          {:ok, project} ->
            {:ok, "frozen:#{project.slug}:#{input.arguments.reason}"}

          {:error, error} ->
            {:error, error}
        end
      end
    end
  end

  policies do
    policy action(:archive) do
      authorize_if actor_attribute_equals(:role, :admin)
    end

    policy always() do
      authorize_if always()
    end
  end

  aggregates do
    count :open_ticket_count, :tickets do
      filter expr(status == :open)
      public? true
    end
  end

  relationships do
    has_many :tickets, Tracker.Delivery.Ticket do
      public? true
    end
  end
end
HARBOR_EOF

RUN cat > /home/user/tracker/lib/tracker/delivery/ticket.ex <<'HARBOR_EOF'
defmodule Tracker.Delivery.Ticket do
  @moduledoc false
  use Ash.Resource,
    otp_app: :tracker,
    domain: Tracker.Delivery,
    data_layer: Ash.DataLayer.Ets

  ets do
    private? true
  end

  attributes do
    uuid_primary_key :id

    attribute :title, :string, allow_nil?: false, public?: true

    attribute :status, Tracker.Delivery.TicketStatus,
      allow_nil?: false,
      default: :open,
      public?: true

    attribute :severity, :integer, allow_nil?: false, default: 1, public?: true
    attribute :estimate_points, :integer, allow_nil?: false, default: 0, public?: true
    attribute :sequence, :integer, allow_nil?: false, default: 0, public?: true
    attribute :internal_reference, :string, public?: true
  end

  actions do
    defaults [:destroy]

    read :read do
      primary? true
      pagination keyset?: true, offset?: true, required?: false
    end

    read :top_severity do
      prepare build(sort: [severity: :desc, sequence: :asc], limit: 1)
    end

    create :create do
      primary? true

      accept [
        :title,
        :status,
        :severity,
        :estimate_points,
        :sequence,
        :internal_reference,
        :project_id,
        :assignee_id
      ]

      argument :labels, {:array, :map}

      change manage_relationship(:labels, type: :create)

      validate string_length(:title, min: 3), message: "must be at least 3 characters"
    end

    update :update do
      primary? true
      require_atomic? false
      accept [:title, :status, :severity, :estimate_points, :assignee_id]

      validate string_length(:title, min: 3), message: "must be at least 3 characters"
    end
  end

  calculations do
    calculate :risk_score, :integer, expr(severity * ^arg(:weight) + estimate_points) do
      public? true

      argument :weight, :integer do
        allow_nil? false
      end
    end
  end

  relationships do
    belongs_to :project, Tracker.Delivery.Project do
      allow_nil? false
      attribute_writable? true
      public? true
    end

    belongs_to :assignee, Tracker.Delivery.User do
      attribute_writable? true
      public? true
    end

    many_to_many :labels, Tracker.Delivery.Label do
      through Tracker.Delivery.TicketLabel
      source_attribute_on_join_resource :ticket_id
      destination_attribute_on_join_resource :label_id
      public? true
    end
  end
end
HARBOR_EOF

RUN cat > /home/user/tracker/lib/tracker/delivery/seed.ex <<'HARBOR_EOF'
defmodule Tracker.Delivery.Seed do
  @moduledoc false
  alias Tracker.Delivery.{Label, Project, Ticket, TicketLabel, User}

  def alice_id, do: "11111111-1111-1111-1111-111111111111"
  def bob_id, do: "22222222-2222-2222-2222-222222222222"
  def apollo_id, do: "aaaaaaaa-0000-0000-0000-000000000001"
  def zephyr_id, do: "aaaaaaaa-0000-0000-0000-000000000002"
  def bug_id, do: "bbbbbbbb-0000-0000-0000-000000000001"
  def ux_id, do: "bbbbbbbb-0000-0000-0000-000000000002"
  def perf_id, do: "bbbbbbbb-0000-0000-0000-000000000003"
  def ticket_id(n), do: "cccccccc-0000-0000-0000-00000000000#{n}"

  def seed! do
    Ash.Seed.seed!(User, %{
      id: alice_id(),
      email: "alice@example.com",
      display_name: "Alice",
      role: :admin,
      internal_notes: "founder"
    })

    Ash.Seed.seed!(User, %{
      id: bob_id(),
      email: "bob@example.com",
      display_name: "Bob",
      role: :member,
      internal_notes: "contractor"
    })

    Ash.Seed.seed!(Project, %{
      id: apollo_id(),
      name: "Apollo",
      slug: "apollo",
      archived: false
    })

    Ash.Seed.seed!(Project, %{
      id: zephyr_id(),
      name: "Zephyr",
      slug: "zephyr",
      archived: false
    })

    Ash.Seed.seed!(Label, %{id: bug_id(), name: "bug", colour: "#c0392b"})
    Ash.Seed.seed!(Label, %{id: ux_id(), name: "ux", colour: "#8e44ad"})
    Ash.Seed.seed!(Label, %{id: perf_id(), name: "perf", colour: "#16a085"})

    tickets = [
      %{
        id: ticket_id(1),
        title: "Login fails on Safari",
        status: :open,
        severity: 5,
        estimate_points: 3,
        sequence: 1,
        internal_reference: "APOLLO-1",
        project_id: apollo_id(),
        assignee_id: alice_id()
      },
      %{
        id: ticket_id(2),
        title: "Improve empty state",
        status: :in_progress,
        severity: 2,
        estimate_points: 5,
        sequence: 2,
        internal_reference: "APOLLO-2",
        project_id: apollo_id(),
        assignee_id: bob_id()
      },
      %{
        id: ticket_id(3),
        title: "Slow dashboard",
        status: :open,
        severity: 4,
        estimate_points: 8,
        sequence: 3,
        internal_reference: "APOLLO-3",
        project_id: apollo_id(),
        assignee_id: alice_id()
      },
      %{
        id: ticket_id(4),
        title: "Broken CSV export",
        status: :blocked,
        severity: 3,
        estimate_points: 2,
        sequence: 4,
        internal_reference: "APOLLO-4",
        project_id: apollo_id(),
        assignee_id: nil
      },
      %{
        id: ticket_id(5),
        title: "Update docs",
        status: :done,
        severity: 1,
        estimate_points: 1,
        sequence: 5,
        internal_reference: "APOLLO-5",
        project_id: apollo_id(),
        assignee_id: bob_id()
      },
      %{
        id: ticket_id(6),
        title: "Zephyr smoke test",
        status: :open,
        severity: 2,
        estimate_points: 13,
        sequence: 6,
        internal_reference: "ZEPHYR-1",
        project_id: zephyr_id(),
        assignee_id: nil
      }
    ]

    Enum.each(tickets, &Ash.Seed.seed!(Ticket, &1))

    join = fn ticket, label ->
      Ash.Seed.seed!(TicketLabel, %{ticket_id: ticket, label_id: label})
    end

    join.(ticket_id(1), bug_id())
    join.(ticket_id(2), ux_id())
    join.(ticket_id(3), bug_id())
    join.(ticket_id(3), perf_id())
    join.(ticket_id(5), ux_id())

    :ok
  end
end
HARBOR_EOF

# Fetch and compile every dependency at build time so that solving and verifying
# the task never needs the network.
RUN cd /home/user/tracker && \
    (for i in 1 2 3 4 5 6; do mix deps.get && break; sleep 10; done) && \
    mix deps.compile && \
    mix compile && \
    rm -rf /tmp/mix_lock* /tmp/mix_pubsub* && \
    chmod 1777 /tmp && \
    chmod -R a+rwX /home/user/tracker && \
    chown -R 1000:1000 /home/user

ENV HEX_OFFLINE=1

LABEL Author="generate-harbor-tasks"
LABEL Description="Offline Elixir 1.18.4 / OTP 27.3.4 environment with an ETS backed Ash 3.31.0 project at /home/user/tracker whose GraphQL layer (ash_graphql 1.10.0 + absinthe 1.11.0) has to be built."

CMD ["/bin/bash", "-c", "trap : TERM INT; sleep infinity & wait"]

# Container contents:
#   - always required apt packages: curl wget ca-certificates git python3 python3-pip python3-pytest bash ripgrep
#   - always required pip3 packages: pytest-json-ctrf
#   - Erlang/OTP 27.3.4 and Elixir 1.18.4 installed from builds.hex.pm into /opt
#   - global MIX_HOME=/opt/mix and HEX_HOME=/opt/hex so any user builds offline
#   - /home/user/tracker: Mix project ":tracker" pinning ash 3.31.0, ash_graphql 1.10.0,
#     absinthe 1.11.0 and simple_sat, with deps fetched and compiled at build time and
#     HEX_OFFLINE=1 afterwards
#   - /home/user/tracker/lib/tracker/delivery{,.ex}: the finished ETS backed Ash domain
#     (User, Project, Ticket, Label, TicketLabel), the TicketStatus/UserRole enums, the
#     SprintFrozen exception and the deterministic Seed fixture module
#   - /home/user/tracker/lib/tracker/graphql_schema.ex is deliberately absent

COPY test_initial_state.py /bootstrap/test_initial_state.py

# Setup entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
