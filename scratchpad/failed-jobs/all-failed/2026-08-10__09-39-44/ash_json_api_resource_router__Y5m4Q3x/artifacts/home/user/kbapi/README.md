# kbapi

An Ash Framework 3.x knowledge base. The `Kbapi.Knowledge` domain owns five
ETS-backed resources (`Author`, `Article`, `Tag`, `ArticleTag`, `Comment`) and a
deterministic `Kbapi.Knowledge.Fixtures` module.

There is no HTTP layer yet.

    mix compile
    mix run <script.exs>

All dependencies are vendored and pre-compiled; the container has no network
access, so `mix deps.get` must not be needed.
