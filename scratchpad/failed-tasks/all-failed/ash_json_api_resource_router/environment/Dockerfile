FROM ubuntu:24.04

ARG POCHI_VERSION
ARG OTP_VERSION=27.3.4
ARG ELIXIR_VERSION=1.18.4

ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=C.UTF-8

RUN apt-get update -y && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        curl wget ca-certificates git python3 python3-pip python3-pytest bash ripgrep \
        unzip libncurses6 libssl3 locales && \
    ln -s /usr/bin/python3 /usr/bin/python && \
    curl -fsSL https://getpochi.com/install.sh | bash -s ${POCHI_VERSION} && \
    ln -s /root/.pochi/bin/pochi /usr/local/bin/pochi && \
    pip3 install --break-system-packages pytest-json-ctrf && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

RUN mkdir -p /home/user && chmod 0755 /home/user

# Pinned Erlang/OTP and Elixir builds, architecture aware (amd64 and arm64).
RUN mkdir -p /opt/otp && \
    curl -fsSL --retry 8 --retry-delay 5 --retry-all-errors \
        -o /tmp/otp.tar.gz \
        "https://builds.hex.pm/builds/otp/$(dpkg --print-architecture)/ubuntu-24.04/OTP-${OTP_VERSION}.tar.gz" && \
    tar -xzf /tmp/otp.tar.gz -C /opt/otp --strip-components=1 && \
    rm -f /tmp/otp.tar.gz && \
    cd /opt/otp && ./Install -minimal /opt/otp

RUN mkdir -p /opt/elixir && \
    curl -fsSL --retry 8 --retry-delay 5 --retry-all-errors \
        -o /tmp/elixir.zip \
        "https://builds.hex.pm/builds/elixir/v${ELIXIR_VERSION}-otp-27.zip" && \
    unzip -q /tmp/elixir.zip -d /opt/elixir && \
    rm -f /tmp/elixir.zip

ENV PATH=/opt/otp/bin:/opt/elixir/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
ENV MIX_HOME=/opt/mix
ENV HEX_HOME=/opt/hex
ENV ERL_AFLAGS="-kernel shell_history enabled"

RUN mkdir -p /opt/mix /opt/hex && \
    (for i in 1 2 3 4 5 6; do mix local.hex --force && exit 0; sleep 10; done; exit 1) && \
    (for i in 1 2 3 4 5 6; do mix local.rebar --force && exit 0; sleep 10; done; exit 1) && \
    chmod -R a+rX /opt/mix /opt/hex

RUN mkdir -p /home/user/kbapi/lib/kbapi/knowledge /home/user/kbapi/config

RUN cat > /home/user/kbapi/mix.exs <<'HARBOR_EOF'
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
HARBOR_EOF
RUN cat > /home/user/kbapi/README.md <<'HARBOR_EOF'
# kbapi

An Ash Framework 3.x knowledge base. The `Kbapi.Knowledge` domain owns five
ETS-backed resources (`Author`, `Article`, `Tag`, `ArticleTag`, `Comment`) and a
deterministic `Kbapi.Knowledge.Fixtures` module.

There is no HTTP layer yet.

    mix compile
    mix run <script.exs>

All dependencies are vendored and pre-compiled; the container has no network
access, so `mix deps.get` must not be needed.
HARBOR_EOF
RUN mkdir -p /home/user/kbapi/config && cat > /home/user/kbapi/config/config.exs <<'HARBOR_EOF'
import Config

config :kbapi, ash_domains: [Kbapi.Knowledge]
config :logger, level: :warning
HARBOR_EOF
RUN mkdir -p /home/user/kbapi/lib && cat > /home/user/kbapi/lib/application.ex <<'HARBOR_EOF'
defmodule Kbapi.Application do
  @moduledoc false
  use Application

  @impl true
  def start(_type, _args) do
    Supervisor.start_link([], strategy: :one_for_one, name: Kbapi.Supervisor)
  end
end
HARBOR_EOF
RUN mkdir -p /home/user/kbapi/lib/kbapi && cat > /home/user/kbapi/lib/kbapi/knowledge.ex <<'HARBOR_EOF'
defmodule Kbapi.Knowledge do
  use Ash.Domain, otp_app: :kbapi

  resources do
    resource Kbapi.Knowledge.Author
    resource Kbapi.Knowledge.Article
    resource Kbapi.Knowledge.Tag
    resource Kbapi.Knowledge.ArticleTag
    resource Kbapi.Knowledge.Comment
  end
end
HARBOR_EOF
RUN mkdir -p /home/user/kbapi/lib/kbapi/knowledge && cat > /home/user/kbapi/lib/kbapi/knowledge/author.ex <<'HARBOR_EOF'
defmodule Kbapi.Knowledge.Author do
  use Ash.Resource,
    otp_app: :kbapi,
    domain: Kbapi.Knowledge,
    data_layer: Ash.DataLayer.Ets

  ets do
    private? true
  end

  attributes do
    uuid_primary_key :id
    attribute :name, :string, allow_nil?: false, public?: true
    attribute :handle, :string, allow_nil?: false, public?: true
    attribute :bio, :string, public?: true

    attribute :role, :atom,
      public?: true,
      default: :reader,
      constraints: [one_of: [:reader, :editor, :admin]]
  end

  relationships do
    has_many :articles, Kbapi.Knowledge.Article do
      public? true
    end
  end

  actions do
    default_accept []
    defaults [:read, :destroy]

    create :create do
      primary? true
      accept [:name, :handle, :bio, :role]
    end

    update :update do
      primary? true
      accept [:name, :bio]
    end
  end
end
HARBOR_EOF
RUN mkdir -p /home/user/kbapi/lib/kbapi/knowledge && cat > /home/user/kbapi/lib/kbapi/knowledge/article.ex <<'HARBOR_EOF'
defmodule Kbapi.Knowledge.Article do
  use Ash.Resource,
    otp_app: :kbapi,
    domain: Kbapi.Knowledge,
    data_layer: Ash.DataLayer.Ets

  ets do
    private? true
  end

  attributes do
    uuid_primary_key :id
    attribute :title, :string, allow_nil?: false, public?: true, constraints: [min_length: 3]
    attribute :slug, :string, allow_nil?: false, public?: true
    attribute :body, :string, public?: true

    attribute :status, :atom,
      public?: true,
      default: :draft,
      constraints: [one_of: [:draft, :published, :archived]]

    attribute :rank, :integer, public?: true, default: 0
    attribute :word_count, :integer, public?: true, default: 0
  end

  relationships do
    belongs_to :author, Kbapi.Knowledge.Author do
      public? true
      allow_nil? false
      attribute_writable? true
    end

    has_many :comments, Kbapi.Knowledge.Comment do
      public? true
    end

    many_to_many :tags, Kbapi.Knowledge.Tag do
      public? true
      through Kbapi.Knowledge.ArticleTag
      source_attribute_on_join_resource :article_id
      destination_attribute_on_join_resource :tag_id
    end
  end

  aggregates do
    count :comment_count, :comments do
      public? true
    end
  end

  actions do
    default_accept []
    defaults [:read, :destroy]

    create :create do
      primary? true
      accept [:title, :slug, :body, :status, :rank, :word_count, :author_id]
    end

    update :update do
      primary? true
      accept [:title, :body, :status, :rank, :word_count]
    end
  end
end
HARBOR_EOF
RUN mkdir -p /home/user/kbapi/lib/kbapi/knowledge && cat > /home/user/kbapi/lib/kbapi/knowledge/tag.ex <<'HARBOR_EOF'
defmodule Kbapi.Knowledge.Tag do
  use Ash.Resource,
    otp_app: :kbapi,
    domain: Kbapi.Knowledge,
    data_layer: Ash.DataLayer.Ets

  ets do
    private? true
  end

  attributes do
    uuid_primary_key :id
    attribute :name, :string, allow_nil?: false, public?: true
    attribute :slug, :string, allow_nil?: false, public?: true
  end

  relationships do
    many_to_many :articles, Kbapi.Knowledge.Article do
      public? true
      through Kbapi.Knowledge.ArticleTag
      source_attribute_on_join_resource :tag_id
      destination_attribute_on_join_resource :article_id
    end
  end

  actions do
    default_accept []
    defaults [:read, :destroy]

    create :create do
      primary? true
      accept [:name, :slug]
    end

    update :update do
      primary? true
      accept [:name, :slug]
    end
  end
end
HARBOR_EOF
RUN mkdir -p /home/user/kbapi/lib/kbapi/knowledge && cat > /home/user/kbapi/lib/kbapi/knowledge/article_tag.ex <<'HARBOR_EOF'
defmodule Kbapi.Knowledge.ArticleTag do
  use Ash.Resource,
    otp_app: :kbapi,
    domain: Kbapi.Knowledge,
    data_layer: Ash.DataLayer.Ets

  ets do
    private? true
  end

  relationships do
    belongs_to :article, Kbapi.Knowledge.Article do
      primary_key? true
      allow_nil? false
      attribute_writable? true
    end

    belongs_to :tag, Kbapi.Knowledge.Tag do
      primary_key? true
      allow_nil? false
      attribute_writable? true
    end
  end

  actions do
    default_accept []
    defaults [:read, :destroy]

    create :create do
      primary? true
      accept [:article_id, :tag_id]
    end
  end
end
HARBOR_EOF
RUN mkdir -p /home/user/kbapi/lib/kbapi/knowledge && cat > /home/user/kbapi/lib/kbapi/knowledge/comment.ex <<'HARBOR_EOF'
defmodule Kbapi.Knowledge.Comment do
  use Ash.Resource,
    otp_app: :kbapi,
    domain: Kbapi.Knowledge,
    data_layer: Ash.DataLayer.Ets

  ets do
    private? true
  end

  attributes do
    uuid_primary_key :id
    attribute :body, :string, allow_nil?: false, public?: true, constraints: [min_length: 2]
    attribute :approved, :boolean, public?: true, default: false
  end

  relationships do
    belongs_to :article, Kbapi.Knowledge.Article do
      public? true
      allow_nil? false
      attribute_writable? true
    end
  end

  actions do
    default_accept []
    defaults [:read, :destroy]

    create :create do
      primary? true
      accept [:body, :article_id]
    end
  end
end
HARBOR_EOF
RUN mkdir -p /home/user/kbapi/lib/kbapi/knowledge && cat > /home/user/kbapi/lib/kbapi/knowledge/fixtures.ex <<'HARBOR_EOF'
defmodule Kbapi.Knowledge.Fixtures do
  @moduledoc """
  Deterministic fixture data for the knowledge base.

  Do not modify this module. The verification suite calls `reset!/0` before every
  scenario and looks records up through the `*_id/1` helpers.
  """

  alias Kbapi.Knowledge.{Article, ArticleTag, Author, Comment, Tag}

  @authors %{
    ada: %{
      id: "11111111-1111-1111-1111-111111111101",
      name: "Ada Lovelace",
      handle: "ada",
      bio: "Writes about analytical engines.",
      role: :editor
    },
    bob: %{
      id: "11111111-1111-1111-1111-111111111102",
      name: "Bob Reader",
      handle: "bob",
      bio: nil,
      role: :reader
    },
    cleo: %{
      id: "11111111-1111-1111-1111-111111111103",
      name: "Cleo Root",
      handle: "cleo",
      bio: "Runs the knowledge base.",
      role: :admin
    }
  }

  @tags %{
    elixir: %{id: "22222222-2222-2222-2222-222222222201", name: "Elixir", slug: "elixir"},
    otp: %{id: "22222222-2222-2222-2222-222222222202", name: "OTP", slug: "otp"},
    web: %{id: "22222222-2222-2222-2222-222222222203", name: "Web", slug: "web"}
  }

  @articles %{
    elixir_basics: %{
      id: "33333333-3333-3333-3333-333333333301",
      title: "Elixir Basics",
      slug: "elixir-basics",
      body: "Pattern matching and pipes.",
      status: :published,
      rank: 30,
      word_count: 1200,
      author: :ada,
      tags: [:elixir, :otp]
    },
    otp_supervisors: %{
      id: "33333333-3333-3333-3333-333333333302",
      title: "OTP Supervisors",
      slug: "otp-supervisors",
      body: "Restart strategies explained.",
      status: :published,
      rank: 20,
      word_count: 800,
      author: :ada,
      tags: [:otp]
    },
    web_drafts: %{
      id: "33333333-3333-3333-3333-333333333303",
      title: "Web Drafts",
      slug: "web-drafts",
      body: nil,
      status: :draft,
      rank: 10,
      word_count: 300,
      author: :cleo,
      tags: [:web]
    },
    archived_notes: %{
      id: "33333333-3333-3333-3333-333333333304",
      title: "Archived Notes",
      slug: "archived-notes",
      body: "Old material.",
      status: :archived,
      rank: 40,
      word_count: 50,
      author: :bob,
      tags: []
    }
  }

  @comments %{
    first: %{
      id: "44444444-4444-4444-4444-444444444401",
      body: "First!",
      approved: true,
      article: :elixir_basics
    },
    second: %{
      id: "44444444-4444-4444-4444-444444444402",
      body: "Second thoughts.",
      approved: false,
      article: :elixir_basics
    },
    third: %{
      id: "44444444-4444-4444-4444-444444444403",
      body: "Nice write up.",
      approved: false,
      article: :otp_supervisors
    }
  }

  def author_id(key), do: @authors |> Map.fetch!(key) |> Map.fetch!(:id)
  def tag_id(key), do: @tags |> Map.fetch!(key) |> Map.fetch!(:id)
  def article_id(key), do: @articles |> Map.fetch!(key) |> Map.fetch!(:id)
  def comment_id(key), do: @comments |> Map.fetch!(key) |> Map.fetch!(:id)

  def reset! do
    Enum.each([Comment, ArticleTag, Article, Tag, Author], fn resource ->
      resource
      |> Ash.read!(authorize?: false)
      |> Enum.each(&Ash.destroy!(&1, authorize?: false))
    end)

    Enum.each(@authors, fn {_key, attrs} -> Ash.Seed.seed!(Author, attrs) end)
    Enum.each(@tags, fn {_key, attrs} -> Ash.Seed.seed!(Tag, attrs) end)

    Enum.each(@articles, fn {_key, attrs} ->
      Ash.Seed.seed!(Article, %{
        id: attrs.id,
        title: attrs.title,
        slug: attrs.slug,
        body: attrs.body,
        status: attrs.status,
        rank: attrs.rank,
        word_count: attrs.word_count,
        author_id: author_id(attrs.author)
      })

      Enum.each(attrs.tags, fn tag ->
        Ash.Seed.seed!(ArticleTag, %{article_id: attrs.id, tag_id: tag_id(tag)})
      end)
    end)

    Enum.each(@comments, fn {_key, attrs} ->
      Ash.Seed.seed!(Comment, %{
        id: attrs.id,
        body: attrs.body,
        approved: attrs.approved,
        article_id: article_id(attrs.article)
      })
    end)

    :ok
  end
end
HARBOR_EOF

# Fetch and compile every dependency at build time so the container needs no
# network access afterwards, and pin them with a committed mix.lock.
RUN cd /home/user/kbapi && \
    (for i in 1 2 3 4 5 6; do mix deps.get && exit 0; sleep 10; done; exit 1) && \
    mix deps.compile && \
    mix compile && \
    MIX_ENV=test mix compile && \
    rm -rf /tmp/mix_lock* /tmp/mix_pubsub* && \
    chmod 1777 /tmp && \
    chmod -R a+rwX /home/user/kbapi

ENV HEX_OFFLINE=1
ENV MIX_ENV=dev

WORKDIR /home/user/kbapi

LABEL Author="generate-harbor-tasks"
LABEL Description="Elixir 1.18.4 / OTP 27.3.4 with a pre-compiled Ash 3.31 + ash_json_api 1.7 knowledge-base project at /home/user/kbapi that has no HTTP layer yet."

CMD ["/bin/bash", "-c", "trap : TERM INT; sleep infinity & wait"]

# Container contents:
#   - always required apt packages: curl wget ca-certificates git python3 python3-pip python3-pytest bash ripgrep
#   - always required pip3 packages: pytest-json-ctrf
#   - Erlang/OTP 27.3.4 and Elixir 1.18.4 installed from builds.hex.pm into /opt/otp and /opt/elixir
#   - /home/user/kbapi: Mix project for the :kbapi OTP app
#   - /home/user/kbapi/mix.exs + mix.lock: ash 3.31, ash_json_api 1.7, plug, open_api_spex, jason, simple_sat
#   - /home/user/kbapi/deps + _build: every dependency vendored and pre-compiled for dev and test (HEX_OFFLINE=1)
#   - /home/user/kbapi/lib/kbapi/knowledge.ex: the Ash domain (no JSON:API extension yet)
#   - /home/user/kbapi/lib/kbapi/knowledge/*.ex: Author, Article, Tag, ArticleTag and Comment resources on Ash.DataLayer.Ets
#   - /home/user/kbapi/lib/kbapi/knowledge/fixtures.ex: deterministic seed data with reset!/0
#   - no HTTP layer: lib/kbapi/api/ does not exist

COPY test_initial_state.py /bootstrap/test_initial_state.py

# Setup entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
