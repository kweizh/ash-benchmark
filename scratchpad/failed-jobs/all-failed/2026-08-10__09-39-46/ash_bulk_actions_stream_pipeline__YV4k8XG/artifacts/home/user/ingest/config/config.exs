import Config

config :ingest, ash_domains: [Ingest.Pipeline]
config :logger, level: :warning
config :ash, :policies, no_filter_static_forbidden_reads?: true
