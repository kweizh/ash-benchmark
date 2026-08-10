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
