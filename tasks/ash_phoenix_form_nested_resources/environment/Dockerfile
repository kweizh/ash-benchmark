FROM ubuntu:24.04

ARG POCHI_VERSION
ARG OTP_VERSION=27.3.4
ARG ELIXIR_VERSION=1.18.4

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update -y && \
    apt-get install -y --no-install-recommends \
        curl wget ca-certificates git python3 python3-pip python3-pytest bash ripgrep \
        unzip libncurses6 libssl3t64 && \
    ln -s /usr/bin/python3 /usr/bin/python && \
    curl -fsSL https://getpochi.com/install.sh | bash -s ${POCHI_VERSION} && \
    ln -s /root/.pochi/bin/pochi /usr/local/bin/pochi && \
    pip3 install --break-system-packages pytest-json-ctrf && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Pinned Erlang/OTP + Elixir builds from builds.hex.pm (arch aware, works for amd64 and arm64).
RUN mkdir -p /opt/otp /opt/elixir && \
    ARCH="$(dpkg --print-architecture)" && \
    curl -fsSL --retry 8 --retry-delay 5 --retry-all-errors \
        -o /tmp/otp.tar.gz \
        "https://builds.hex.pm/builds/otp/${ARCH}/ubuntu-24.04/OTP-${OTP_VERSION}.tar.gz" && \
    tar -xzf /tmp/otp.tar.gz -C /opt/otp --strip-components=1 && \
    cd /opt/otp && ./Install -minimal /opt/otp && \
    curl -fsSL --retry 8 --retry-delay 5 --retry-all-errors \
        -o /tmp/elixir.zip \
        "https://builds.hex.pm/builds/elixir/v${ELIXIR_VERSION}-otp-27.zip" && \
    unzip -q /tmp/elixir.zip -d /opt/elixir && \
    rm -f /tmp/otp.tar.gz /tmp/elixir.zip

ENV PATH="/opt/otp/bin:/opt/elixir/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
ENV MIX_HOME=/opt/mix
ENV HEX_HOME=/opt/hex
ENV ELIXIR_ERL_OPTIONS="+fnu"

RUN mkdir -p /opt/mix /opt/hex && \
    (for i in 1 2 3 4 5 6; do mix local.hex --force && exit 0; sleep 10; done; exit 1) && \
    (for i in 1 2 3 4 5 6; do mix local.rebar --force && exit 0; sleep 10; done; exit 1) && \
    chmod -R a+rX /opt/mix /opt/hex

RUN mkdir -p /home/user && chmod 0755 /home/user
RUN mkdir -p /home/user/catering/config /home/user/catering/lib/catering/orders

RUN cat > /home/user/catering/mix.exs <<'EOF'
defmodule Catering.MixProject do
  use Mix.Project

  def project do
    [
      app: :catering,
      version: "0.1.0",
      elixir: "~> 1.18",
      start_permanent: Mix.env() == :prod,
      deps: deps()
    ]
  end

  def application do
    [
      extra_applications: [:logger]
    ]
  end

  defp deps do
    [
      {:ash, "~> 3.0"},
      {:ash_phoenix, "~> 2.0"}
    ]
  end
end
EOF

RUN cat > /home/user/catering/mix.lock <<'EOF'
%{
  "ash": {:hex, :ash, "3.31.0", "9ccd7d5ff00a5329a33786063e4a3040681b61d736730cd7aa3f24e5843c1d4f", [:mix], [{:crux, ">= 0.1.2 and < 1.0.0-0", [hex: :crux, repo: "hexpm", optional: false]}, {:decimal, "~> 2.0 or ~> 3.0", [hex: :decimal, repo: "hexpm", optional: false]}, {:ecto, "~> 3.14", [hex: :ecto, repo: "hexpm", optional: false]}, {:ets, "~> 0.8", [hex: :ets, repo: "hexpm", optional: false]}, {:igniter, ">= 0.6.29 and < 1.0.0-0", [hex: :igniter, repo: "hexpm", optional: true]}, {:jason, ">= 1.0.0", [hex: :jason, repo: "hexpm", optional: false]}, {:picosat_elixir, "~> 0.2", [hex: :picosat_elixir, repo: "hexpm", optional: true]}, {:plug, ">= 0.0.0", [hex: :plug, repo: "hexpm", optional: true]}, {:reactor, "~> 1.0", [hex: :reactor, repo: "hexpm", optional: false]}, {:simple_sat, ">= 0.1.1 and < 1.0.0-0", [hex: :simple_sat, repo: "hexpm", optional: true]}, {:spark, ">= 2.6.0", [hex: :spark, repo: "hexpm", optional: false]}, {:splode, "~> 0.3", [hex: :splode, repo: "hexpm", optional: false]}, {:stream_data, "~> 1.0", [hex: :stream_data, repo: "hexpm", optional: false]}, {:telemetry, "~> 1.1", [hex: :telemetry, repo: "hexpm", optional: false]}], "hexpm", "7518ecf694e1b423478ddaa5baf713e9d38448df6873f3be6316f758bc6ab68d"},
  "ash_phoenix": {:hex, :ash_phoenix, "2.3.24", "950b69bcb0fec099f65c1fb8f2e28efca509b17f14da6750301208169fd51875", [:mix], [{:ash, ">= 3.5.13 and < 4.0.0-0", [hex: :ash, repo: "hexpm", optional: false]}, {:igniter, "~> 0.6", [hex: :igniter, repo: "hexpm", optional: true]}, {:inertia, "~> 2.3", [hex: :inertia, repo: "hexpm", optional: true]}, {:phoenix, "~> 1.5.6 or ~> 1.6", [hex: :phoenix, repo: "hexpm", optional: false]}, {:phoenix_html, "~> 4.0", [hex: :phoenix_html, repo: "hexpm", optional: false]}, {:phoenix_live_view, "~> 0.20.3 or ~> 1.0-rc.1", [hex: :phoenix_live_view, repo: "hexpm", optional: false]}, {:spark, ">= 2.2.29 and < 3.0.0-0", [hex: :spark, repo: "hexpm", optional: false]}], "hexpm", "46e3209cfe5063c0e8d39cad98198cb8fbbccf9df6b29075c3ae45576f94c467"},
  "crux": {:hex, :crux, "0.1.4", "1fa21f5ca886d3498f83871a3ef19379b80abf8cfcf2ed32007e80279e714f1e", [:mix], [{:picosat_elixir, "~> 0.2", [hex: :picosat_elixir, repo: "hexpm", optional: true]}, {:simple_sat, ">= 0.1.1 and < 1.0.0-0", [hex: :simple_sat, repo: "hexpm", optional: true]}, {:stream_data, "~> 1.0", [hex: :stream_data, repo: "hexpm", optional: true]}], "hexpm", "ff7d880cf732d82360aa81e439b8d4831cd30768061c9233f90c97e10162b9c0"},
  "decimal": {:hex, :decimal, "3.1.1", "430d87b04011ce6cbd4fd205be758311a81f87d552d40904abd00f015935b1d0", [:mix], [], "hexpm", "c5f25f2ced74a0587d03e6023f595db8e924c9d3922c8c8ffd9edfc4498cf1f6"},
  "ecto": {:hex, :ecto, "3.14.1", "7b740d87bdf45996aa0c2c2e081640906f10caa7ce5ba328fd294c7d49d0cc6f", [:mix], [{:decimal, "~> 3.0", [hex: :decimal, repo: "hexpm", optional: false]}, {:jason, "~> 1.0", [hex: :jason, repo: "hexpm", optional: true]}, {:telemetry, "~> 0.4 or ~> 1.0", [hex: :telemetry, repo: "hexpm", optional: false]}], "hexpm", "24b991956796700f467d0a3ef3d303138a3ef9ddddf8b98f43758ee067b20a30"},
  "ets": {:hex, :ets, "0.9.0", "79c6a6c205436780486f72d84230c6cba2f8a9920456750ddd1e47389107d5fd", [:mix], [], "hexpm", "2861fdfb04bcaeff370f1a5904eec864f0a56dcfebe5921ea9aadf2a481c822b"},
  "iterex": {:hex, :iterex, "0.1.2", "58f9b9b9a22a55cbfc7b5234a9c9c63eaac26d276b3db80936c0e1c60355a5a6", [:mix], [], "hexpm", "2e103b8bcc81757a9af121f6dc0df312c9a17220f302b1193ef720460d03029d"},
  "jason": {:hex, :jason, "1.4.5", "2e3a008590b0b8d7388c20293e9dcc9cf3e5d642fd2a114e4cbbb52e595d940a", [:mix], [{:decimal, "~> 1.0 or ~> 2.0 or ~> 3.0", [hex: :decimal, repo: "hexpm", optional: true]}], "hexpm", "b0c823996102bcd0239b3c2444eb00409b72f6a140c1950bc8b457d836b30684"},
  "mime": {:hex, :mime, "2.0.7", "b8d739037be7cd402aee1ba0306edfdef982687ee7e9859bee6198c1e7e2f128", [:mix], [], "hexpm", "6171188e399ee16023ffc5b76ce445eb6d9672e2e241d2df6050f3c771e80ccd"},
  "multigraph": {:hex, :multigraph, "0.16.1-mg.4", "2bbe149f5411b0e3bf0624c7bf2e3da2738efeac2f9a67bbbcb807ab171f0a76", [:mix], [], "hexpm", "b9f3e2577cef4658eeedf97c76d22a86d33a7aab702a93c1da9c122e849e9037"},
  "phoenix": {:hex, :phoenix, "1.8.9", "a63ed0962ed5b903b146dab0ae8eb8387fe478f8171a5e26d56a165f35996fe1", [:mix], [{:bandit, "~> 1.0", [hex: :bandit, repo: "hexpm", optional: true]}, {:jason, "~> 1.0", [hex: :jason, repo: "hexpm", optional: true]}, {:phoenix_pubsub, "~> 2.1", [hex: :phoenix_pubsub, repo: "hexpm", optional: false]}, {:phoenix_template, "~> 1.0", [hex: :phoenix_template, repo: "hexpm", optional: false]}, {:phoenix_view, "~> 2.0", [hex: :phoenix_view, repo: "hexpm", optional: true]}, {:plug, "~> 1.14", [hex: :plug, repo: "hexpm", optional: false]}, {:plug_cowboy, "~> 2.7", [hex: :plug_cowboy, repo: "hexpm", optional: true]}, {:plug_crypto, "~> 1.2 or ~> 2.0", [hex: :plug_crypto, repo: "hexpm", optional: false]}, {:telemetry, "~> 0.4 or ~> 1.0", [hex: :telemetry, repo: "hexpm", optional: false]}, {:websock_adapter, "~> 0.5", [hex: :websock_adapter, repo: "hexpm", optional: false]}], "hexpm", "3477e2dd5a4f61820341169031bdfe21275f659923bea9c5c0ea2aa1c3fcc046"},
  "phoenix_html": {:hex, :phoenix_html, "4.3.0", "d3577a5df4b6954cd7890c84d955c470b5310bb49647f0a114a6eeecc850f7ad", [:mix], [], "hexpm", "3eaa290a78bab0f075f791a46a981bbe769d94bc776869f4f3063a14f30497ad"},
  "phoenix_live_view": {:hex, :phoenix_live_view, "1.2.8", "5006fd7b429c42489600fbc1600c750d0f0e5b5ea4965d9758e429b979392991", [:mix], [{:igniter, ">= 0.6.16 and < 1.0.0-0", [hex: :igniter, repo: "hexpm", optional: true]}, {:jason, "~> 1.0", [hex: :jason, repo: "hexpm", optional: true]}, {:lazy_html, "~> 0.1.0", [hex: :lazy_html, repo: "hexpm", optional: true]}, {:phoenix, "~> 1.6.15 or ~> 1.7.0 or ~> 1.8.0", [hex: :phoenix, repo: "hexpm", optional: false]}, {:phoenix_html, "~> 3.3 or ~> 4.0", [hex: :phoenix_html, repo: "hexpm", optional: false]}, {:phoenix_template, "~> 1.0", [hex: :phoenix_template, repo: "hexpm", optional: false]}, {:phoenix_view, "~> 2.0", [hex: :phoenix_view, repo: "hexpm", optional: true]}, {:plug, "~> 1.15", [hex: :plug, repo: "hexpm", optional: false]}, {:telemetry, "~> 0.4.2 or ~> 1.0", [hex: :telemetry, repo: "hexpm", optional: false]}], "hexpm", "b05ffe21f43c0ff219da62948b482c324aa5b8873e17b0c0cac58289a178af38"},
  "phoenix_pubsub": {:hex, :phoenix_pubsub, "2.2.0", "ff3a5616e1bed6804de7773b92cbccfc0b0f473faf1f63d7daf1206c7aeaaa6f", [:mix], [], "hexpm", "adc313a5bf7136039f63cfd9668fde73bba0765e0614cba80c06ac9460ff3e96"},
  "phoenix_template": {:hex, :phoenix_template, "1.0.4", "e2092c132f3b5e5b2d49c96695342eb36d0ed514c5b252a77048d5969330d639", [:mix], [{:phoenix_html, "~> 2.14.2 or ~> 3.0 or ~> 4.0", [hex: :phoenix_html, repo: "hexpm", optional: true]}], "hexpm", "2c0c81f0e5c6753faf5cca2f229c9709919aba34fab866d3bc05060c9c444206"},
  "plug": {:hex, :plug, "1.20.3", "56c480c633ec2ce10140e236e15233bf576e1d323887d7c96711bd02ab5160db", [:mix], [{:mime, "~> 1.0 or ~> 2.0", [hex: :mime, repo: "hexpm", optional: false]}, {:plug_crypto, "~> 1.1.1 or ~> 1.2 or ~> 2.0", [hex: :plug_crypto, repo: "hexpm", optional: false]}, {:telemetry, "~> 0.4.3 or ~> 1.0", [hex: :telemetry, repo: "hexpm", optional: false]}], "hexpm", "be266aee1b8536ef6409d58cf39a3121319f0ec47cfa1b24024485aa0e76ad76"},
  "plug_crypto": {:hex, :plug_crypto, "2.2.0", "144014737daaf485407f5ed77daeaad74d651b216a28c87543f8cc7043f8efc8", [:mix], [], "hexpm", "83a95744ab1c75876542b6fab135fcc176280e0f301a111c1f757fddcec95d2c"},
  "reactor": {:hex, :reactor, "1.0.5", "43a3298fb5874248e72d61662704d5013194c427afcf740e14336f3379f53ed3", [:mix], [{:igniter, "~> 0.4", [hex: :igniter, repo: "hexpm", optional: true]}, {:iterex, "~> 0.1", [hex: :iterex, repo: "hexpm", optional: false]}, {:jason, "~> 1.0", [hex: :jason, repo: "hexpm", optional: false]}, {:multigraph, "~> 0.16.1-mg.2", [hex: :multigraph, repo: "hexpm", optional: false]}, {:spark, ">= 2.3.3 and < 3.0.0-0", [hex: :spark, repo: "hexpm", optional: false]}, {:splode, "~> 0.2", [hex: :splode, repo: "hexpm", optional: false]}, {:telemetry, "~> 1.2", [hex: :telemetry, repo: "hexpm", optional: false]}, {:yaml_elixir, "~> 2.11", [hex: :yaml_elixir, repo: "hexpm", optional: false]}, {:ymlr, "~> 5.0", [hex: :ymlr, repo: "hexpm", optional: false]}], "hexpm", "8867decb795d0b87a9dea5d146721af60312c0b45443d125d9be535946e8da19"},
  "spark": {:hex, :spark, "2.7.2", "36becc6ff03b40908cc821d403d7f06d893498e293d2f718afc6ca097fcb9d93", [:mix], [{:igniter, ">= 0.3.64 and < 1.0.0-0", [hex: :igniter, repo: "hexpm", optional: true]}, {:jason, "~> 1.4", [hex: :jason, repo: "hexpm", optional: true]}, {:sourceror, "~> 1.2", [hex: :sourceror, repo: "hexpm", optional: true]}], "hexpm", "adb323ddbf9dbbe326f9e5def54ac96c47911e852b2c270bb19a5147c56f1b45"},
  "splode": {:hex, :splode, "0.3.2", "7716b6b2260a98a6f018c65cc0393da2cdf17314202eb351a0956e8762190dff", [:mix], [], "hexpm", "08fd658f80da7f1cd254b149164dcff8acd44b22f032001d5416b97223d32bc9"},
  "stream_data": {:hex, :stream_data, "1.4.0", "026f929db613aabea6208012ae9b8970d3fd5f88b3bdf26831bc536f98c42036", [:mix], [], "hexpm", "2b0ee3a340dcce1c8cf6302a763ee757d1e01c54d6e16d9069062509d68b1dc9"},
  "telemetry": {:hex, :telemetry, "1.4.2", "a0cb522801dffb1c49fe6e30561badffc7b6d0e180db1300df759faa22062855", [:rebar3], [], "hexpm", "928f6495066506077862c0d1646609eed891a4326bee3126ba54b60af61febb1"},
  "websock": {:hex, :websock, "0.5.3", "2f69a6ebe810328555b6fe5c831a851f485e303a7c8ce6c5f675abeb20ebdadc", [:mix], [], "hexpm", "6105453d7fac22c712ad66fab1d45abdf049868f253cf719b625151460b8b453"},
  "websock_adapter": {:hex, :websock_adapter, "0.6.0", "73db5ab8aaefd1a876a97ce3e6afc96562625de69ef17a4e04426e034849d0b8", [:mix], [{:bandit, ">= 0.6.0", [hex: :bandit, repo: "hexpm", optional: true]}, {:plug, "~> 1.14", [hex: :plug, repo: "hexpm", optional: false]}, {:plug_cowboy, "~> 2.6", [hex: :plug_cowboy, repo: "hexpm", optional: true]}, {:websock, "~> 0.5", [hex: :websock, repo: "hexpm", optional: false]}], "hexpm", "50021a85bce8f203b086705d9e0c5415e2c7eb05d319111b0428fe71f9934617"},
  "yamerl": {:hex, :yamerl, "0.10.0", "4ff81fee2f1f6a46f1700c0d880b24d193ddb74bd14ef42cb0bcf46e81ef2f8e", [:rebar3], [], "hexpm", "346adb2963f1051dc837a2364e4acf6eb7d80097c0f53cbdc3046ec8ec4b4e6e"},
  "yaml_elixir": {:hex, :yaml_elixir, "2.12.2", "9dd1330fb4cd9a36a7b0f502e5b12486eff632792ee4a5f0eba52a4d4ec32c9c", [:mix], [{:yamerl, "~> 0.10", [hex: :yamerl, repo: "hexpm", optional: false]}], "hexpm", "e7c1b10122f973e6558462d51c39026ba0e14afbc6745318e990ea82cfe9e159"},
  "ymlr": {:hex, :ymlr, "5.1.6", "247479328fd5ea1e222ee59ecd5571ab2885cf1a6329aea458d4944cd035cfc1", [:mix], [], "hexpm", "b36d7c72384d2cb2094d2a3c8b0c3b12303e0ccd1b7b12333b81d75b1fe0b53a"},
}
EOF

RUN cat > /home/user/catering/config/config.exs <<'EOF'
import Config

config :catering, ash_domains: [Catering.Orders]
config :logger, level: :warning
EOF

RUN cat > /home/user/catering/lib/catering/orders.ex <<'EOF'
defmodule Catering.Orders do
  use Ash.Domain, otp_app: :catering

  resources do
    resource Catering.Orders.Customer
    resource Catering.Orders.Order
    resource Catering.Orders.LineItem
    resource Catering.Orders.Modifier
  end
end
EOF

RUN cat > /home/user/catering/lib/catering/orders/customer.ex <<'EOF'
defmodule Catering.Orders.Customer do
  use Ash.Resource,
    otp_app: :catering,
    domain: Catering.Orders,
    data_layer: Ash.DataLayer.Ets

  ets do
    private? true
  end

  attributes do
    uuid_primary_key :id
    attribute :name, :string, allow_nil?: false, public?: true
    attribute :email, :string, allow_nil?: false, public?: true
  end

  actions do
    defaults [:read, :destroy]
    default_accept [:name, :email]

    create :register do
      primary? true
      accept [:name, :email]
    end

    update :amend do
      primary? true
      accept [:name, :email]
    end
  end
end
EOF

RUN cat > /home/user/catering/lib/catering/orders/order.ex <<'EOF'
defmodule Catering.Orders.Order do
  use Ash.Resource,
    otp_app: :catering,
    domain: Catering.Orders,
    data_layer: Ash.DataLayer.Ets

  ets do
    private? true
  end

  attributes do
    uuid_primary_key :id
    attribute :reference, :string, allow_nil?: false, public?: true
    attribute :note, :string, public?: true

    attribute :delivery_windows, {:array, Catering.Orders.DeliveryWindow} do
      public? true
      default []
    end

    attribute :fulfillment, Catering.Orders.Fulfillment do
      public? true
    end
  end

  relationships do
    belongs_to :customer, Catering.Orders.Customer do
      public? true
      attribute_writable? true
    end

    has_many :line_items, Catering.Orders.LineItem do
      public? true
    end
  end

  actions do
    defaults [:read, :destroy]
    default_accept [:reference, :note, :delivery_windows, :fulfillment]

    create :place do
      accept [:reference, :note, :delivery_windows, :fulfillment]
      argument :customer, :map
      argument :line_items, {:array, :map}

      change manage_relationship(:customer,
               on_lookup: :relate,
               on_no_match: :create,
               on_match: :ignore
             )

      change manage_relationship(:line_items, type: :direct_control, order_is_key: :position)
    end

    update :revise do
      require_atomic? false
      accept [:reference, :note, :delivery_windows, :fulfillment]
      argument :line_items, {:array, :map}

      change manage_relationship(:line_items, type: :direct_control, order_is_key: :position)
    end
  end
end
EOF

RUN cat > /home/user/catering/lib/catering/orders/line_item.ex <<'EOF'
defmodule Catering.Orders.LineItem do
  use Ash.Resource,
    otp_app: :catering,
    domain: Catering.Orders,
    data_layer: Ash.DataLayer.Ets

  ets do
    private? true
  end

  attributes do
    uuid_primary_key :id
    attribute :dish, :string, allow_nil?: false, public?: true
    attribute :quantity, :integer, allow_nil?: false, default: 1, public?: true
    attribute :position, :integer, allow_nil?: false, default: 0, public?: true
  end

  relationships do
    belongs_to :order, Catering.Orders.Order do
      public? true
      attribute_writable? true
    end

    has_many :modifiers, Catering.Orders.Modifier do
      public? true
    end
  end

  actions do
    defaults [:read, :destroy]
    default_accept [:dish, :quantity, :position]

    create :add do
      primary? true
      accept [:dish, :quantity, :position]
      argument :modifiers, {:array, :map}
      change manage_relationship(:modifiers, type: :direct_control, order_is_key: :position)
    end

    update :revise do
      primary? true
      require_atomic? false
      accept [:dish, :quantity, :position]
      argument :modifiers, {:array, :map}
      change manage_relationship(:modifiers, type: :direct_control, order_is_key: :position)
    end
  end

  validations do
    validate compare(:quantity, greater_than: 0), message: "must be positive"
  end
end
EOF

RUN cat > /home/user/catering/lib/catering/orders/modifier.ex <<'EOF'
defmodule Catering.Orders.Modifier do
  use Ash.Resource,
    otp_app: :catering,
    domain: Catering.Orders,
    data_layer: Ash.DataLayer.Ets

  ets do
    private? true
  end

  attributes do
    uuid_primary_key :id
    attribute :label, :string, allow_nil?: false, public?: true
    attribute :surcharge_cents, :integer, allow_nil?: false, default: 0, public?: true
    attribute :position, :integer, allow_nil?: false, default: 0, public?: true
  end

  relationships do
    belongs_to :line_item, Catering.Orders.LineItem do
      public? true
      attribute_writable? true
    end
  end

  actions do
    defaults [:read, :destroy]
    default_accept [:label, :surcharge_cents, :position]

    create :add do
      primary? true
      accept [:label, :surcharge_cents, :position]
    end

    update :revise do
      primary? true
      accept [:label, :surcharge_cents, :position]
    end
  end

  validations do
    validate compare(:surcharge_cents, greater_than_or_equal_to: 0),
      message: "must not be negative"
  end
end
EOF

RUN cat > /home/user/catering/lib/catering/orders/delivery_window.ex <<'EOF'
defmodule Catering.Orders.DeliveryWindow do
  use Ash.Resource,
    data_layer: :embedded

  attributes do
    uuid_primary_key :id, writable?: true
    attribute :label, :string, allow_nil?: false, public?: true
    attribute :starts_at_minute, :integer, allow_nil?: false, public?: true
    attribute :ends_at_minute, :integer, allow_nil?: false, public?: true
  end

  actions do
    defaults [:read, :destroy, create: :*, update: :*]
  end

  validations do
    validate compare(:ends_at_minute, greater_than: :starts_at_minute),
      message: "must be after the start"
  end
end
EOF

RUN cat > /home/user/catering/lib/catering/orders/fulfillment.ex <<'EOF'
defmodule Catering.Orders.CourierDrop do
  use Ash.Resource, data_layer: :embedded

  attributes do
    attribute :kind, :string, public?: true
    attribute :street, :string, allow_nil?: false, public?: true
    attribute :postcode, :string, allow_nil?: false, public?: true
  end

  actions do
    defaults [:read, :destroy, create: :*, update: :*]
  end
end

defmodule Catering.Orders.CounterPickup do
  use Ash.Resource, data_layer: :embedded

  attributes do
    attribute :kind, :string, public?: true
    attribute :counter, :string, allow_nil?: false, public?: true
  end

  actions do
    defaults [:read, :destroy, create: :*, update: :*]
  end
end

defmodule Catering.Orders.Fulfillment do
  use Ash.Type.NewType,
    subtype_of: :union,
    constraints: [
      types: [
        courier: [
          type: Catering.Orders.CourierDrop,
          tag: :kind,
          tag_value: "courier"
        ],
        pickup: [
          type: Catering.Orders.CounterPickup,
          tag: :kind,
          tag_value: "pickup"
        ]
      ]
    ]
end
EOF

RUN cat > /home/user/catering/lib/catering/forms.ex <<'EOF'
defmodule Catering.Forms do
  @moduledoc """
  Facade that the LiveView layer uses to build, mutate, inspect and submit the
  nested catering order form.

  Every function below is an unimplemented stub.
  """

  @todo "Catering.Forms is not implemented yet"

  def new_order_form, do: raise(@todo)

  def edit_order_form(_order_id), do: raise(@todo)

  def to_phoenix_form(_form), do: raise(@todo)

  def change(_form, _params, _opts \\ []), do: raise(@todo)

  def add_nested(_form, _path, _opts \\ []), do: raise(@todo)

  def remove_nested(_form, _path), do: raise(@todo)

  def reorder(_form, _path, _order), do: raise(@todo)

  def move(_form, _path, _direction), do: raise(@todo)

  def submitted_params(_form), do: raise(@todo)

  def hidden_inputs(_form, _path), do: raise(@todo)

  def error_map(_form), do: raise(@todo)

  def raw_error_list(_form, _path), do: raise(@todo)

  def serialize(_form), do: raise(@todo)

  def save(_form, _params \\ nil), do: raise(@todo)
end
EOF


WORKDIR /home/user/catering

RUN (for i in 1 2 3 4 5 6; do mix deps.get && exit 0; sleep 10; done; exit 1) && \
    mix deps.compile && \
    mix compile && \
    rm -rf /tmp/mix_lock* /tmp/mix_pubsub* && \
    chmod 1777 /tmp && \
    chmod -R a+rwX /home/user && \
    chown -R 1000:1000 /home/user

ENV HEX_OFFLINE=1

LABEL Author="generate-harbor-tasks"
LABEL Description="Offline Elixir 1.18.4 / OTP 27.3.4 environment with a compiled Ash 3.31.0 + ash_phoenix 2.3.24 catering-order domain at /home/user/catering and an unimplemented Catering.Forms nested-form facade."

CMD ["/bin/bash", "-c", "trap : TERM INT; sleep infinity & wait"]

# Container contents:
#   - always required apt packages: curl wget ca-certificates git python3 python3-pip python3-pytest bash ripgrep
#   - always required pip3 packages: pytest-json-ctrf
#   - Erlang/OTP 27.3.4 and Elixir 1.18.4 installed from builds.hex.pm into /opt/otp and /opt/elixir
#   - Hex and rebar3 vendored into /opt/hex and /opt/mix; HEX_OFFLINE=1 so no network is needed
#   - /home/user/catering: Mix project `catering` with ash 3.31.0 and ash_phoenix 2.3.24 pinned in mix.lock,
#     dependencies fetched and compiled at build time
#   - /home/user/catering/lib/catering/orders.ex and lib/catering/orders/*.ex: the pre-built Ash domain
#     (Order, LineItem, Modifier, Customer, the embedded DeliveryWindow, and the CourierDrop/CounterPickup
#     union members) backed by the in-memory ETS data layer
#   - /home/user/catering/lib/catering/forms.ex: an unimplemented Catering.Forms stub for the executor to write

COPY test_initial_state.py /bootstrap/test_initial_state.py

# Setup entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
