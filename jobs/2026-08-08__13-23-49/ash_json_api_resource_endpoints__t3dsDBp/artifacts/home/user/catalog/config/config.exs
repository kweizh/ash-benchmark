import Config

config :catalog, ash_domains: [Catalog.Library]

# JSON:API media type registration.
config :mime,
  extensions: %{"json" => "application/vnd.api+json"},
  types: %{"application/vnd.api+json" => ["json"]}

config :logger, level: :warning
