# vault

An event-sourced account ledger built on Ash Framework v3 with the in-memory ETS
data layer.

The project ships only the OTP application module and `Vault.Ledger.Hook`. The
`Vault.Ledger` domain, its resources and the event-sourcing modules are yours to
write.

Useful commands (the container is offline; all dependencies are already fetched
and compiled):

    mix compile
    mix run <script.exs>
