import Config

config :tracker, ash_domains: [Tracker.Delivery]

config :logger, level: :warning

config :ash, :policies, show_policy_breakdowns?: false
