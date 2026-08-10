import Config

config :billing,
  ash_domains: [Billing.Metering],
  ecto_repos: [Billing.Repo]

config :billing, Billing.Repo,
  username: "postgres",
  password: "postgres",
  hostname: "127.0.0.1",
  port: 5432,
  database: "billing_dev",
  pool_size: 20,
  queue_target: 5000,
  queue_interval: 10_000,
  log: false

config :logger, level: :warning
