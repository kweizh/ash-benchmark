defmodule Logistics.Repo do
  use AshPostgres.Repo, otp_app: :logistics

  @impl AshPostgres.Repo
  def min_pg_version do
    %Version{major: 16, minor: 0, patch: 0}
  end

  @impl AshPostgres.Repo
  def installed_extensions do
    ["ash-functions", "citext", "uuid-ossp"]
  end
end
