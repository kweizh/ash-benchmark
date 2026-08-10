import Config

config :sla_lab, ash_domains: [SlaLab.Ops]

config :ash, :custom_expressions, [SlaLab.Expressions.RouteKey, SlaLab.Expressions.RatioBps]

config :logger, level: :warning
