import Config

config :outbox, ash_domains: [Outbox.Ledger, Outbox.Eventing]

config :logger, level: :warning
