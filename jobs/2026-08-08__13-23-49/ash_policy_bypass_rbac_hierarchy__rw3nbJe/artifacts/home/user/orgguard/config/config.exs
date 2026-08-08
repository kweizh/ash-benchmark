import Config

# The OrgGuard access-control domain.
config :orgguard,
  ash_domains: [OrgGuard.Access]

# Keep the ETS data layer's debug chatter out of stdout.
config :logger, level: :warning
