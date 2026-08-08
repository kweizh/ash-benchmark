"""Final-state verification for the ash_json_api_resource_endpoints task.

Everything is checked against the real, running service: the `:catalog` OTP
application is booted once with `mix run --no-halt`, and every assertion is made
on the raw HTTP status codes, headers and JSON bodies it returns on
http://127.0.0.1:4001/api/json.
"""

import os
import socket
import uuid
from typing import Any, Dict, List, Optional
from urllib.parse import unquote

import pytest
import requests
from xprocess import ProcessStarter

PROJECT_DIR = "/home/user/catalog"
HOST = "127.0.0.1"
PORT = 4001
BASE = f"http://{HOST}:{PORT}/api/json"
JSONAPI = "application/vnd.api+json"

PLAIN_HEADERS = {"Content-Type": JSONAPI, "Accept": JSONAPI}
CURATOR_HEADERS = {**PLAIN_HEADERS, "x-actor-role": "curator"}

MISSING_ID = "11111111-1111-1111-1111-111111111111"


# --------------------------------------------------------------------------- #
# service lifecycle
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="session")
def service(xprocess):
    class Starter(ProcessStarter):
        name = "catalog_api"
        args = ["mix", "run", "--no-halt"]  # type: ignore[assignment]
        env = {**os.environ, "MIX_ENV": "dev"}
        popen_kwargs = {"cwd": PROJECT_DIR, "text": True}
        timeout = 150
        terminate_on_interrupt = True

        def startup_check(self):  # type: ignore[override]
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(2)
                if sock.connect_ex((HOST, PORT)) != 0:
                    return False
            try:
                resp = requests.get(f"{BASE}/authors", headers=PLAIN_HEADERS, timeout=20)
            except requests.RequestException:
                return False
            return resp.status_code < 500

    info = xprocess.getinfo(Starter.name)
    printed = 0

    def dump(tag: str) -> None:
        nonlocal printed
        try:
            with open(info.logpath, "r", encoding="utf-8", errors="replace") as handle:
                lines = handle.readlines()
        except OSError:
            return
        new = lines[printed:]
        printed = len(lines)
        print(f"===== [{tag}] catalog_api log =====")
        print("".join(new))
        print(f"===== [{tag}] end catalog_api log =====")

    started = False
    try:
        xprocess.ensure(Starter.name, Starter)
        started = True
    finally:
        dump("STARTED" if started else "FAILED")

    yield

    dump("TEARDOWN")
    info.terminate()


# --------------------------------------------------------------------------- #
# HTTP helpers
# --------------------------------------------------------------------------- #
def _get(path: str, params: Optional[Dict[str, Any]] = None, curator: bool = False):
    headers = CURATOR_HEADERS if curator else PLAIN_HEADERS
    return requests.get(BASE + path, params=params, headers=headers, timeout=60)


def _post(path: str, payload: Dict[str, Any], curator: bool = False):
    headers = CURATOR_HEADERS if curator else PLAIN_HEADERS
    return requests.post(BASE + path, json=payload, headers=headers, timeout=60)


def _patch(path: str, payload: Dict[str, Any], curator: bool = False):
    headers = CURATOR_HEADERS if curator else PLAIN_HEADERS
    return requests.patch(BASE + path, json=payload, headers=headers, timeout=60)


def _delete(path: str, curator: bool = False):
    headers = CURATOR_HEADERS if curator else PLAIN_HEADERS
    return requests.delete(BASE + path, headers=headers, timeout=60)


def _body(resp: requests.Response) -> Dict[str, Any]:
    try:
        parsed = resp.json()
    except ValueError:
        raise AssertionError(
            f"{resp.request.method} {resp.request.url} returned a non-JSON body "
            f"(status {resp.status_code}): {resp.text[:800]!r}"
        )
    assert isinstance(parsed, dict), (
        f"{resp.request.method} {resp.request.url} returned a JSON value that is not an "
        f"object: {parsed!r}"
    )
    return parsed


def _ok(resp: requests.Response, expected: int) -> Dict[str, Any]:
    assert resp.status_code == expected, (
        f"{resp.request.method} {resp.request.url} returned {resp.status_code}, "
        f"expected {expected}. Body: {resp.text[:800]!r}"
    )
    return _body(resp)


def _errors(resp: requests.Response, expected_status: int) -> List[Dict[str, Any]]:
    body = _ok(resp, expected_status)
    assert "data" not in body, (
        f"An error document for {resp.request.url} must not carry a `data` member, got "
        f"{sorted(body)}"
    )
    errors = body.get("errors")
    assert isinstance(errors, list) and errors, (
        f"Expected a non-empty top-level `errors` array from {resp.request.url}, got {body!r}"
    )
    return errors


def _ids(data: Any) -> List[str]:
    assert isinstance(data, list), f"Expected `data` to be an array, got {data!r}"
    return [item["id"] for item in data]


def _create_author(name: str, country: str) -> str:
    resp = _post(
        "/authors",
        {"data": {"type": "author", "attributes": {"name": name, "country": country}}},
    )
    body = _ok(resp, 201)
    return body["data"]["id"]


def _book_payload(
    title: str, shelf: str, year: int, price_cents: int, author_id: str, restricted: bool
) -> Dict[str, Any]:
    return {
        "data": {
            "type": "book",
            "attributes": {
                "title": title,
                "shelf": shelf,
                "year": year,
                "price_cents": price_cents,
                "restricted": restricted,
            },
            "relationships": {"author": {"data": {"type": "author", "id": author_id}}},
        }
    }


def _create_book(
    title: str,
    shelf: str,
    year: int,
    price_cents: int,
    author_id: str,
    restricted: bool = False,
) -> str:
    resp = _post("/books", _book_payload(title, shelf, year, price_cents, author_id, restricted))
    body = _ok(resp, 201)
    return body["data"]["id"]


def _create_review(book_id: str, rating: int, text: str) -> str:
    resp = _post(
        "/reviews",
        {
            "data": {
                "type": "review",
                "attributes": {"rating": rating, "body": text},
                "relationships": {"book": {"data": {"type": "book", "id": book_id}}},
            }
        },
    )
    body = _ok(resp, 201)
    return body["data"]["id"]


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="session")
def fx(service) -> Dict[str, Any]:
    shelf = "shelf-" + uuid.uuid4().hex[:10]
    write_shelf = shelf + "-w"

    a1 = _create_author("Le Guin", "US")
    a2 = _create_author("Lem", "PL")

    alpha = _create_book("Alpha", shelf, 1969, 1200, a1)
    beta = _create_book("Beta", shelf, 1974, 900, a1)
    gamma = _create_book("Gamma", shelf, 1961, 1500, a2)
    delta = _create_book("Delta", shelf, 1980, 500, a2, restricted=True)

    r1 = _create_review(alpha, 5, "great")
    r2 = _create_review(alpha, 3, "ok")
    _create_review(gamma, 4, "fine")

    return {
        "shelf": shelf,
        "write_shelf": write_shelf,
        "a1": a1,
        "a2": a2,
        "alpha": alpha,
        "beta": beta,
        "gamma": gamma,
        "delta": delta,
        "alpha_reviews": {r1, r2},
    }


# --------------------------------------------------------------------------- #
# 1. resource object shape
# --------------------------------------------------------------------------- #
def test_t01_get_one_book_resource_object(fx):
    resp = _get(f"/books/{fx['alpha']}")
    body = _ok(resp, 200)
    assert resp.headers.get("content-type", "").startswith(JSONAPI), (
        f"Expected the {JSONAPI} content type, got {resp.headers.get('content-type')!r}"
    )
    data = body["data"]
    assert data["type"] == "book", f"Expected data.type 'book', got {data.get('type')!r}"
    assert data["id"] == fx["alpha"], f"Expected data.id {fx['alpha']}, got {data.get('id')!r}"
    assert set(data["attributes"]) == {
        "title",
        "shelf",
        "year",
        "price_cents",
        "restricted",
    }, f"Unexpected book attribute keys: {sorted(data['attributes'])}"
    assert data["attributes"] == {
        "title": "Alpha",
        "shelf": fx["shelf"],
        "year": 1969,
        "price_cents": 1200,
        "restricted": False,
    }, f"Book attribute values are wrong: {data['attributes']!r}"


def test_t02_top_level_document_members_and_self_link(fx):
    body = _ok(_get(f"/books/{fx['alpha']}"), 200)
    for key in ("data", "links", "meta", "jsonapi"):
        assert key in body, f"Top-level member {key!r} missing from the document: {sorted(body)}"
    assert body["jsonapi"].get("version") == "1.0", (
        f"Expected jsonapi.version '1.0', got {body['jsonapi']!r}"
    )
    expected = f"{BASE}/books/{fx['alpha']}"
    assert body["links"].get("self") == expected, (
        f"Expected top-level links.self {expected}, got {body['links'].get('self')!r}"
    )
    assert body["data"]["links"].get("self") == expected, (
        f"Expected the book resource links.self {expected}, got {body['data'].get('links')!r}"
    )


def test_t03_sparse_fieldset_on_primary_data(fx):
    body = _ok(_get(f"/books/{fx['alpha']}", {"fields[book]": "title,year"}), 200)
    attrs = body["data"]["attributes"]
    assert set(attrs) == {"title", "year"}, (
        f"fields[book]=title,year must yield exactly those attributes, got {sorted(attrs)}"
    )
    assert attrs == {"title": "Alpha", "year": 1969}, f"Wrong sparse attribute values: {attrs!r}"


def test_t04_include_author_linkage_and_included(fx):
    body = _ok(_get(f"/books/{fx['alpha']}", {"include": "author"}), 200)
    linkage = body["data"]["relationships"]["author"].get("data")
    assert linkage == {"type": "author", "id": fx["a1"]}, (
        f"Expected author linkage {{'type': 'author', 'id': {fx['a1']!r}}}, got {linkage!r}"
    )
    included = body.get("included")
    assert isinstance(included, list) and len(included) == 1, (
        f"Expected exactly one included resource, got {included!r}"
    )
    assert included[0]["type"] == "author" and included[0]["id"] == fx["a1"], (
        f"Included resource is not author {fx['a1']}: {included[0]!r}"
    )
    assert included[0]["attributes"]["name"] == "Le Guin", (
        f"Included author has the wrong name: {included[0]['attributes']!r}"
    )


def test_t05_sparse_fieldset_applies_to_included(fx):
    body = _ok(
        _get(f"/books/{fx['alpha']}", {"include": "author", "fields[author]": "name"}), 200
    )
    included = body["included"]
    assert len(included) == 1, f"Expected one included author, got {included!r}"
    assert set(included[0]["attributes"]) == {"name"}, (
        f"fields[author]=name must restrict included attributes to `name`, got "
        f"{sorted(included[0]['attributes'])}"
    )


# --------------------------------------------------------------------------- #
# 2. index, filtering, includes
# --------------------------------------------------------------------------- #
def test_t06_index_filter_hides_restricted_from_anonymous(fx):
    body = _ok(_get("/books", {"filter[shelf]": fx["shelf"]}), 200)
    got = set(_ids(body["data"]))
    assert got == {fx["alpha"], fx["beta"], fx["gamma"]}, (
        "An anonymous caller must see exactly the three unrestricted books, got "
        f"{sorted(got)}"
    )
    assert all(item["type"] == "book" for item in body["data"]), (
        f"Every entry must have type 'book': {body['data']!r}"
    )


def test_t07_index_filter_shows_restricted_to_curator(fx):
    body = _ok(_get("/books", {"filter[shelf]": fx["shelf"]}, curator=True), 200)
    got = set(_ids(body["data"]))
    assert got == {fx["alpha"], fx["beta"], fx["gamma"], fx["delta"]}, (
        f"A curator must see all four books on the shelf, got {sorted(got)}"
    )


def test_t08_included_resources_are_deduplicated(fx):
    body = _ok(
        _get("/books", {"filter[shelf]": fx["shelf"], "include": "author"}, curator=True), 200
    )
    included = body.get("included")
    assert isinstance(included, list), f"Expected an `included` array, got {included!r}"
    keys = [(item["type"], item["id"]) for item in included]
    assert len(keys) == len(set(keys)), f"`included` contains duplicates: {keys!r}"
    assert set(keys) == {("author", fx["a1"]), ("author", fx["a2"])}, (
        f"Expected exactly the two distinct authors in `included`, got {sorted(keys)}"
    )


def test_t09_nested_include_is_complete_and_deduplicated(fx):
    body = _ok(_get(f"/authors/{fx['a1']}", {"include": "books.reviews"}), 200)

    linkage = body["data"]["relationships"]["books"].get("data")
    assert isinstance(linkage, list), f"Expected books linkage array, got {linkage!r}"
    assert {entry["id"] for entry in linkage} == {fx["alpha"], fx["beta"]}, (
        f"books linkage must list Alpha and Beta, got {linkage!r}"
    )
    assert all(entry["type"] == "book" for entry in linkage), (
        f"books linkage entries must be book identifiers: {linkage!r}"
    )

    included = body["included"]
    keys = [(item["type"], item["id"]) for item in included]
    assert len(keys) == len(set(keys)), f"`included` contains duplicates: {keys!r}"
    expected = {("book", fx["alpha"]), ("book", fx["beta"])} | {
        ("review", rid) for rid in fx["alpha_reviews"]
    }
    assert set(keys) == expected, (
        f"Expected included to hold both books and both Alpha reviews, got {sorted(keys)}"
    )

    alpha = next(item for item in included if item["id"] == fx["alpha"])
    review_ids = {entry["id"] for entry in alpha["relationships"]["reviews"]["data"]}
    assert review_ids == fx["alpha_reviews"], (
        f"The included Alpha must expose both review identifiers, got {sorted(review_ids)}"
    )


def test_t10_relationship_links_on_author(fx):
    body = _ok(_get(f"/authors/{fx['a1']}"), 200)
    links = body["data"]["relationships"]["books"]["links"]
    assert links.get("related") == f"{BASE}/authors/{fx['a1']}/books", (
        f"Wrong relationships.books.links.related: {links!r}"
    )
    assert links.get("self") == f"{BASE}/authors/{fx['a1']}/relationships/books", (
        f"Wrong relationships.books.links.self: {links!r}"
    )


# --------------------------------------------------------------------------- #
# 3. sorting and pagination
# --------------------------------------------------------------------------- #
def _titles(body: Dict[str, Any]) -> List[str]:
    return [item["attributes"]["title"] for item in body["data"]]


def test_t11_sort_descending(fx):
    body = _ok(_get("/books", {"filter[shelf]": fx["shelf"], "sort": "-year"}), 200)
    assert _titles(body) == ["Beta", "Alpha", "Gamma"], (
        f"sort=-year must order Beta, Alpha, Gamma; got {_titles(body)}"
    )


def test_t12_sort_ascending(fx):
    body = _ok(_get("/books", {"filter[shelf]": fx["shelf"], "sort": "year"}), 200)
    assert _titles(body) == ["Gamma", "Alpha", "Beta"], (
        f"sort=year must order Gamma, Alpha, Beta; got {_titles(body)}"
    )


def test_t13_pagination_first_page_links_and_total(fx):
    body = _ok(
        _get(
            "/books",
            {
                "filter[shelf]": fx["shelf"],
                "sort": "year",
                "page[limit]": 2,
                "page[offset]": 0,
                "page[count]": "true",
            },
        ),
        200,
    )
    assert _titles(body) == ["Gamma", "Alpha"], f"Wrong first page: {_titles(body)}"
    page = body["meta"]["page"]
    assert page.get("total") == 3, (
        f"meta.page.total must be 3 for an anonymous caller (Delta is hidden), got {page!r}"
    )
    assert page.get("limit") == 2, f"meta.page.limit must be 2, got {page!r}"
    assert page.get("offset") == 0, f"meta.page.offset must be 0, got {page!r}"
    links = body["links"]
    assert links.get("prev") is None, f"links.prev must be null on the first page, got {links!r}"
    assert links.get("next"), f"links.next must be present on the first page, got {links!r}"
    assert "page[offset]=2" in unquote(links["next"]), (
        f"links.next must point at offset 2, got {links['next']!r}"
    )
    assert links.get("first"), f"links.first must be present, got {links!r}"


def test_t14_pagination_last_page_links(fx):
    body = _ok(
        _get(
            "/books",
            {
                "filter[shelf]": fx["shelf"],
                "sort": "year",
                "page[limit]": 2,
                "page[offset]": 2,
                "page[count]": "true",
            },
        ),
        200,
    )
    assert _titles(body) == ["Beta"], f"Wrong second page: {_titles(body)}"
    page = body["meta"]["page"]
    assert page.get("offset") == 2, f"meta.page.offset must be 2, got {page!r}"
    assert page.get("total") == 3, f"meta.page.total must be 3, got {page!r}"
    links = body["links"]
    assert links.get("next") is None, f"links.next must be null on the last page, got {links!r}"
    assert links.get("prev"), f"links.prev must be present on the last page, got {links!r}"


# --------------------------------------------------------------------------- #
# 4. writes
# --------------------------------------------------------------------------- #
def test_t15_create_book_persists_and_links_author(fx):
    resp = _post("/books", _book_payload("Fresh", fx["write_shelf"], 2001, 333, fx["a2"], False))
    created = _ok(resp, 201)
    new_id = created["data"]["id"]
    assert new_id, f"POST /books must return the new id, got {created!r}"

    body = _ok(_get(f"/books/{new_id}", {"include": "author"}), 200)
    attrs = body["data"]["attributes"]
    assert attrs["title"] == "Fresh", f"Persisted title is wrong: {attrs!r}"
    assert attrs["shelf"] == fx["write_shelf"], f"Persisted shelf is wrong: {attrs!r}"
    assert attrs["year"] == 2001, f"Persisted year is wrong: {attrs!r}"
    assert attrs["price_cents"] == 333, f"Persisted price_cents is wrong: {attrs!r}"
    assert attrs["restricted"] is False, f"restricted must default to false: {attrs!r}"
    assert body["data"]["relationships"]["author"]["data"]["id"] == fx["a2"], (
        f"The created book must belong to author {fx['a2']}: {body['data']['relationships']!r}"
    )


def test_t16_multiple_attribute_constraint_violations(fx):
    resp = _post("/books", _book_payload("Bad", fx["write_shelf"], 1200, -5, fx["a2"], False))
    errors = _errors(resp, 400)
    assert len(errors) == 2, f"Expected exactly two error objects, got {errors!r}"
    pointers = {err["source"]["pointer"] for err in errors}
    assert pointers == {"/data/attributes/year", "/data/attributes/price_cents"}, (
        f"Wrong error pointers: {sorted(pointers)}"
    )
    for err in errors:
        assert err["code"] == "invalid_attribute", f"Wrong error code: {err!r}"
        assert err["status"] == "400", f"Wrong error status: {err!r}"
        for key in ("id", "title", "detail"):
            assert key in err, f"Error object is missing {key!r}: {err!r}"


def test_t17_missing_required_attribute(fx):
    payload = _book_payload("x", fx["write_shelf"], 1990, 100, fx["a2"], False)
    del payload["data"]["attributes"]["title"]
    errors = _errors(_post("/books", payload), 400)
    assert any(
        err["code"] == "required" and err["source"].get("pointer") == "/data/attributes/title"
        for err in errors
    ), f"Expected a `required` error pointing at /data/attributes/title, got {errors!r}"


def test_t18_review_rating_out_of_range(fx):
    resp = _post(
        "/reviews",
        {
            "data": {
                "type": "review",
                "attributes": {"rating": 9, "body": "nope"},
                "relationships": {"book": {"data": {"type": "book", "id": fx["alpha"]}}},
            }
        },
    )
    errors = _errors(resp, 400)
    assert any(
        err["code"] == "invalid_attribute"
        and err["source"].get("pointer") == "/data/attributes/rating"
        for err in errors
    ), f"Expected an `invalid_attribute` error on /data/attributes/rating, got {errors!r}"


def test_t19_missing_required_relationship(fx):
    payload = _book_payload("Orphan", fx["write_shelf"], 1990, 100, fx["a2"], False)
    del payload["data"]["relationships"]
    errors = _errors(_post("/books", payload), 400)
    assert any(
        err["code"] == "required"
        and err["source"].get("pointer") == "/data/relationships/author"
        for err in errors
    ), f"Expected a `required` error pointing at /data/relationships/author, got {errors!r}"


def test_t20_wrong_resource_type_in_body(fx):
    payload = _book_payload("Wrong", fx["write_shelf"], 1990, 100, fx["a2"], False)
    payload["data"]["type"] = "volume"
    errors = _errors(_post("/books", payload), 400)
    assert any(
        err["code"] == "invalid_body" and err["source"].get("pointer") == "/data/type"
        for err in errors
    ), f"Expected an `invalid_body` error pointing at /data/type, got {errors!r}"


def test_t21_unknown_id_returns_not_found(fx):
    resp = _get(f"/books/{MISSING_ID}")
    errors = _errors(resp, 404)
    assert resp.headers.get("content-type", "").startswith(JSONAPI), (
        f"Error responses must also use {JSONAPI}, got {resp.headers.get('content-type')!r}"
    )
    assert errors[0]["code"] == "not_found", f"Wrong error code: {errors[0]!r}"
    assert errors[0]["status"] == "404", f"Wrong error status: {errors[0]!r}"


def test_t22_patch_updates_only_the_given_attributes(fx):
    book_id = _create_book("Patchable", fx["write_shelf"], 1995, 700, fx["a2"])
    body = _ok(
        _patch(f"/books/{book_id}", {"data": {"type": "book", "id": book_id, "attributes": {"price_cents": 777}}}),
        200,
    )
    attrs = body["data"]["attributes"]
    assert attrs["price_cents"] == 777, f"PATCH did not apply price_cents: {attrs!r}"
    assert attrs["title"] == "Patchable", f"PATCH must not change the title: {attrs!r}"
    assert attrs["year"] == 1995, f"PATCH must not change the year: {attrs!r}"

    refetched = _ok(_get(f"/books/{book_id}"), 200)["data"]["attributes"]
    assert refetched["price_cents"] == 777, f"The update was not persisted: {refetched!r}"


def test_t23_delete_is_forbidden_without_the_curator_role(fx):
    book_id = _create_book("Doomed", fx["write_shelf"], 1996, 400, fx["a2"])
    errors = _errors(_delete(f"/books/{book_id}"), 403)
    assert errors[0]["code"] == "forbidden", f"Wrong error code: {errors[0]!r}"
    assert errors[0]["status"] == "403", f"Wrong error status: {errors[0]!r}"
    _ok(_get(f"/books/{book_id}"), 200)


def test_t24_curator_can_delete(fx):
    book_id = _create_book("Ephemeral", fx["write_shelf"], 1997, 450, fx["a2"])
    _ok(_delete(f"/books/{book_id}", curator=True), 200)
    resp = _get(f"/books/{book_id}")
    assert resp.status_code == 404, (
        f"A deleted book must answer 404, got {resp.status_code}: {resp.text[:400]!r}"
    )


def test_t25_restricted_book_visibility(fx):
    anon = _get(f"/books/{fx['delta']}")
    assert anon.status_code == 404, (
        f"A restricted book must answer 404 to a non-curator, got {anon.status_code}"
    )
    body = _ok(_get(f"/books/{fx['delta']}", curator=True), 200)
    assert body["data"]["attributes"]["restricted"] is True, (
        f"Delta must be restricted: {body['data']['attributes']!r}"
    )


# --------------------------------------------------------------------------- #
# 5. relationship routes and the report route
# --------------------------------------------------------------------------- #
def test_t26_related_route_returns_full_resource_objects(fx):
    body = _ok(_get(f"/authors/{fx['a1']}/books"), 200)
    assert set(_ids(body["data"])) == {fx["alpha"], fx["beta"]}, (
        f"The related route must return Alpha and Beta, got {_ids(body['data'])}"
    )
    for item in body["data"]:
        assert item["type"] == "book", f"Related entries must be books: {item!r}"
        assert item["attributes"].get("title"), (
            f"Related entries must be full resource objects with attributes: {item!r}"
        )


def test_t27_relationship_route_returns_identifier_objects_only(fx):
    body = _ok(_get(f"/authors/{fx['a1']}/relationships/books"), 200)
    data = body["data"]
    assert isinstance(data, list) and len(data) == 2, (
        f"Expected two resource identifier objects, got {data!r}"
    )
    for entry in data:
        assert set(entry) == {"type", "id"}, (
            f"Resource identifier objects must carry only `type` and `id`, got {sorted(entry)}"
        )
        assert entry["type"] == "book", f"Wrong identifier type: {entry!r}"
    assert {entry["id"] for entry in data} == {fx["alpha"], fx["beta"]}, (
        f"Wrong identifiers: {data!r}"
    )


def test_t28_shelf_summary_report(fx):
    expected = {
        "result": {
            "shelf": fx["shelf"],
            "book_count": 4,
            "review_count": 3,
            "total_price_cents": 4100,
        }
    }
    anon = _ok(_get("/reports/shelf_summary", {"shelf": fx["shelf"]}), 200)
    assert anon == expected, f"Anonymous report body is wrong: {anon!r}"
    curator = _ok(_get("/reports/shelf_summary", {"shelf": fx["shelf"]}, curator=True), 200)
    assert curator == expected, f"Curator report body is wrong: {curator!r}"


def test_t29_shelf_summary_requires_the_shelf_argument(fx):
    errors = _errors(_get("/reports/shelf_summary"), 400)
    assert errors[0]["code"] == "required", (
        f"Expected a `required` error when shelf is omitted, got {errors!r}"
    )


def test_t30_unknown_include_is_rejected(fx):
    errors = _errors(_get(f"/books/{fx['alpha']}", {"include": "publisher"}), 400)
    assert errors[0]["code"] == "invalid_includes", f"Wrong error code: {errors[0]!r}"
    assert errors[0]["source"].get("parameter") == "include", (
        f"Expected source.parameter 'include', got {errors[0]!r}"
    )
