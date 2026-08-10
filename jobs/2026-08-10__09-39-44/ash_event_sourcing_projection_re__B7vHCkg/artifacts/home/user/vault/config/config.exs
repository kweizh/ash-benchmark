import Config

# The Vault.Ledger domain must be implemented by you.
config :vault, ash_domains: [Vault.Ledger]

config :logger, level: :warning
