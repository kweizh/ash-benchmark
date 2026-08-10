defimpl AshGraphql.Error, for: Ash.Error.Unknown.UnknownError do
  @moduledoc false

  def to_error(error) do
    %{
      message: Exception.message(error),
      short_message: Exception.message(error),
      code: "unknown",
      vars: %{},
      fields: []
    }
  end
end
