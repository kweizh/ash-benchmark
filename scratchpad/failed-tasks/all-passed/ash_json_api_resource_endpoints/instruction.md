# Serve an Ash domain as a spec-compliant JSON:API

## Background

`/home/user/catalog` holds an empty Elixir/Mix project for the OTP application `:catalog`. Every dependency it will ever need is already fetched and compiled for both the `dev` and `test` Mix environments (Ash 3.x, `ash_json_api` 1.7.x, `open_api_spex`, `plug`, `bandit`, `jason`, `picosat_elixir`). The machine has **no network access**: do not add, remove, upgrade or re-resolve dependencies, and do not edit `mix.exs` or `mix.lock`.

You must turn this empty project into a book-catalog service that publishes its whole domain as a JSON:API over HTTP, served by the application itself, backed entirely by an in-memory Ash data layer (there is no database in this environment).

## Requirements

### Domain model

Define the Ash domain `Catalog.Library` (`otp_app: :catalog`) with exactly three resources, all using an in-memory data layer:

| Module | JSON:API `type` | Attributes | Relationships |
| --- | --- | --- | --- |
| `Catalog.Library.Author` | `"author"` | `id` (uuid primary key), `name` (string, required, non-empty), `country` (string, optional) | `books` — many `Book` |
| `Catalog.Library.Book` | `"book"` | `id` (uuid primary key), `title` (string, required, non-empty), `shelf` (string, required, non-empty), `year` (integer, required, 1450..2100), `price_cents` (integer, required, >= 0), `restricted` (boolean, required, defaults to `false`) | `author` — one `Author`, required; `reviews` — many `Review` |
| `Catalog.Library.Review` | `"review"` | `id` (uuid primary key), `rating` (integer, required, 1..5), `body` (string, optional) | `book` — one `Book`, required |

A record written through the API must remain readable by every later request for as long as the node is up.

### HTTP surface

Starting the `:catalog` application must start an HTTP server bound to `127.0.0.1` on TCP port `4001`; `mix run --no-halt` inside the project directory must therefore serve the API. Every JSON:API route lives under the URL prefix `/api/json`, so the base URL is `http://127.0.0.1:4001/api/json`. Routes below are written relative to that base URL.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/authors` | list authors |
| POST | `/authors` | create an author |
| GET | `/authors/:id` | fetch one author |
| GET | `/authors/:id/books` | the author's books, as full resource objects |
| GET | `/authors/:id/relationships/books` | the author's books, as resource identifier objects only |
| GET | `/books` | list books |
| POST | `/books` | create a book |
| GET | `/books/:id` | fetch one book |
| PATCH | `/books/:id` | update a book |
| DELETE | `/books/:id` | delete a book |
| GET | `/reviews/:id` | fetch one review |
| POST | `/reviews` | create a review |
| GET | `/reports/shelf_summary` | a non-CRUD report (see below) |

### Document shape

Every response — success or failure — must carry the `Content-Type` header `application/vnd.api+json`.

A successful document has the top-level members `data`, `links`, `meta` and `jsonapi`, with `jsonapi.version` equal to `"1.0"`, and `links.self` equal to the full URL of the request that produced it (query string included, exactly as received). `included` appears only when the request asked for it.

A resource object has the members `type`, `id`, `attributes`, `relationships`, `links` and `meta`. Its `links.self` is the canonical single-resource URL for that record (e.g. `<base>/books/<id>`). The `attributes` object of a `book` contains exactly the keys `title`, `shelf`, `year`, `price_cents` and `restricted` — the primary key and any foreign key must never leak into `attributes`. An `author` exposes exactly `name` and `country`; a `review` exposes exactly `rating` and `body`.

On an `author` resource object, `relationships.books.links.related` must be `<base>/authors/<id>/books` and `relationships.books.links.self` must be `<base>/authors/<id>/relationships/books`.

`GET /authors/:id/relationships/books` returns a `data` array whose entries are resource identifier objects carrying **only** the members `type` and `id`.

### Query features (index and single-resource GETs)

- **Sparse fieldsets** — `fields[<type>]=a,b` restricts the `attributes` of every resource of that type, in `data` and in `included` alike, to exactly the requested keys.
- **Inclusion** — `include=<path>[,<path>]`. `book` must support `author` and `reviews`; `author` must support `books` and the nested path `books.reviews`. Every relationship named by `include` must expose resource identifier linkage under `relationships.<name>.data` on the resources that own it, and `included` must contain every reachable related resource exactly once, with no duplicates.
- **Filtering** — `filter[<attribute>]=<value>` on the book and author list routes.
- **Sorting** — `sort=<field>` and `sort=-<field>` (descending), comma-separated for multiple keys.
- **Pagination** — the book list route accepts `page[limit]` and `page[offset]`. When paginating, `meta.page.limit` and `meta.page.offset` echo the applied values, and `links` gains `first`, `next` and `prev`; `next` is `null` on the final page and `prev` is `null` on the first page. When `page[count]=true` is also supplied, `meta.page.total` must be the total number of records matching the request, ignoring the page window.

### Writes

`POST /books` accepts a document whose `data.type` is `"book"`, whose `data.attributes` carries the book's own attributes, and whose `data.relationships.author.data` is an author resource identifier object. The owning author is settable **only** through that relationship member. `POST /reviews` works the same way with `data.relationships.book.data`. `POST /authors` takes attributes only. `PATCH /books/:id` accepts a partial `data.attributes` object and leaves unmentioned attributes untouched. Successful creation answers `201`; successful fetch, update and deletion answer `200`.

### Errors

Failures answer with a top-level `errors` array (and no `data` member). Each error object carries `id`, `status` (the HTTP status as a string), `code`, `title`, `detail`, plus a `source` object pointing at the cause. The following situations must produce exactly these HTTP statuses and `code` values:

| Situation | Status | `code` | `source` |
| --- | --- | --- | --- |
| single-resource route addressed with an id that does not exist (or is not visible to the caller) | 404 | `not_found` | — |
| submitted attribute violates its constraint | 400 | `invalid_attribute` | `pointer` = `/data/attributes/<attribute>` |
| required attribute missing from the submitted document | 400 | `required` | `pointer` = `/data/attributes/<attribute>` |
| required relationship missing from the submitted document | 400 | `required` | `pointer` = `/data/relationships/<relationship>` |
| `data.type` in a submitted document does not match the route's resource type | 400 | `invalid_body` | `pointer` = `/data/type` |
| `include` names a path the resource does not publish | 400 | `invalid_includes` | `parameter` = `include` |
| the caller is not allowed to perform the action | 403 | `forbidden` | — |

When one document violates several constraints at once, every violation must appear as its own error object.

### Authorization

The caller's identity comes from the request header `x-actor-role`. The value `curator` designates a curator; any other value, or a missing header, designates a caller who is not a curator. The rules are:

- A book whose `restricted` is `true` is invisible to non-curators: it is absent from list results, and `GET /books/<id>` for it answers `404` for a non-curator and `200` for a curator. Pagination totals reported to a non-curator must likewise exclude it.
- `DELETE /books/:id` is allowed only for a curator; for anyone else it answers `403` and the record must still exist afterwards.
- Author and review routes, and book creation and update, are open to everybody.

### The report route

`GET /reports/shelf_summary?shelf=<shelf>` runs a non-CRUD action and answers `200` with the body

```json
{"result": {"shelf": "<shelf>", "book_count": 0, "review_count": 0, "total_price_cents": 0}}
```

where `book_count` is the number of books whose `shelf` equals the argument, `review_count` is the number of reviews attached to those books, and `total_price_cents` is the sum of their `price_cents`. This report always covers **every** matching book, including `restricted` ones, whatever the caller's role. Omitting the `shelf` query parameter answers `400` with an error whose `code` is `required`.

## Implementation Hints

- Project path: `/home/user/catalog`
- Start command (run from the project path): `mix run --no-halt`
- Port: `4001`, bound to `127.0.0.1`; JSON:API base URL `http://127.0.0.1:4001/api/json`
- Requests are sent with `Content-Type: application/vnd.api+json`; verification reads raw JSON bodies and raw HTTP status codes, and never uses any Ash or AshJsonApi test helper.
- All application code must live under `/home/user/catalog/lib`. `mix.exs`, `mix.lock` and everything under `deps/` must remain untouched, and `mix compile` must succeed with the existing dependency set.
- The `:catalog` application must boot cleanly with `MIX_ENV=dev`; verification boots it exactly once and issues every request against the single running node.

