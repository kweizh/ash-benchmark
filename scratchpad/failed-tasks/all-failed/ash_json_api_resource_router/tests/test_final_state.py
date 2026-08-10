"""Final-state verification for the ash_json_api_resource_router task.

The whole JSON:API surface is exercised in-process: a self-contained ExUnit
driver script is written to /tmp and executed with `mix run` inside the project.
The script prints one `@@HARBOR@@<name>@@<status>@@<base64 detail>` line per
scenario, which is mapped back onto one pytest function per scenario so that
every behaviour is reported individually.
"""

import base64
import os
import re
import subprocess

import pytest

PROJECT_DIR = "/home/user/kbapi"
SCRIPT_PATH = "/tmp/harbor_jsonapi_test.exs"
MARKER = "@@HARBOR@@"

HARBOR_SUITE_EXS = r"""
defmodule HarborFormatter do
  @moduledoc false
  use GenServer

  def init(_opts), do: {:ok, %{}}

  def handle_cast({:test_finished, %ExUnit.Test{} = test}, state) do
    {status, detail} =
      case test.state do
        nil ->
          {"passed", ""}

        {:failed, failures} ->
          {"failed",
           ExUnit.Formatter.format_test_failure(test, failures, 1, 120, fn _kind, msg -> msg end)}

        {:invalid, _} ->
          {"failed", "invalid: setup failed"}

        {:skipped, _} ->
          {"skipped", ""}

        {:excluded, _} ->
          {"skipped", ""}
      end

    IO.puts("@@HARBOR@@#{test.name}@@#{status}@@#{Base.encode64(detail)}")
    {:noreply, state}
  end

  def handle_cast(_msg, state), do: {:noreply, state}
end

ExUnit.start(autorun: false, formatters: [HarborFormatter], seed: 0, colors: [enabled: false])

defmodule H do
  @moduledoc false
  @jsonapi "application/vnd.api+json"
  @endpoint Module.concat(["Kbapi", "Api", "Endpoint"])

  def jsonapi, do: @jsonapi

  def endpoint, do: @endpoint

  def request(method, path, opts \\ []) do
    body = Keyword.get(opts, :body, :none)
    actor = Keyword.get(opts, :actor)
    accept = Keyword.get(opts, :accept, @jsonapi)
    content_type = Keyword.get(opts, :content_type, @jsonapi)

    conn =
      case body do
        :none ->
          Plug.Test.conn(method, path)

        value ->
          Plug.Test.conn(method, path, Jason.encode!(value))
          |> Plug.Conn.put_req_header("content-type", content_type)
      end

    conn =
      case accept do
        nil -> conn
        value -> Plug.Conn.put_req_header(conn, "accept", value)
      end

    conn =
      case actor do
        nil -> conn
        handle -> Plug.Conn.put_req_header(conn, "x-actor-handle", handle)
      end

    if Code.ensure_loaded?(@endpoint) and function_exported?(@endpoint, :call, 2) do
      try do
        result = @endpoint.call(conn, @endpoint.init([]))

        %{
          status: result.status,
          raw: result.resp_body,
          body: decode(result.resp_body),
          content_type: List.first(Plug.Conn.get_resp_header(result, "content-type"))
        }
      rescue
        error ->
          %{
            status: :raised,
            raw: Exception.message(error),
            body: nil,
            content_type: nil
          }
      catch
        kind, reason ->
          %{status: :raised, raw: "#{inspect(kind)}: #{inspect(reason)}", body: nil, content_type: nil}
      end
    else
      %{status: :missing_endpoint, raw: "Kbapi.Api.Endpoint is not defined", body: nil, content_type: nil}
    end
  end

  defp decode(binary) when is_binary(binary) do
    case Jason.decode(binary) do
      {:ok, value} -> value
      _ -> nil
    end
  end

  defp decode(_), do: nil

  def follow(url) when is_binary(url) do
    uri = URI.parse(url)
    path = uri.path <> if(uri.query in [nil, ""], do: "", else: "?" <> uri.query)
    request(:get, path)
  end

  def slugs(%{"data" => data}) when is_list(data),
    do: Enum.map(data, &get_in(&1, ["attributes", "slug"]))

  def ids(%{"data" => data}) when is_list(data), do: Enum.map(data, & &1["id"])

  def first_error(%{"errors" => [error | _]}), do: error
  def first_error(_), do: %{}
end

defmodule KbapiJsonApiTest do
  use ExUnit.Case, async: false

  alias Kbapi.Knowledge.Fixtures

  @jsonapi "application/vnd.api+json"

  setup do
    Fixtures.reset!()
    :ok
  end

  defp article(key), do: Fixtures.article_id(key)
  defp author(key), do: Fixtures.author_id(key)
  defp tag(key), do: Fixtures.tag_id(key)
  defp comment(key), do: Fixtures.comment_id(key)

  test "T01 index route returns every fixture article as a json:api resource object" do
    res = H.request(:get, "/api/articles")

    assert res.status == 200, inspect(res)
    assert is_list(res.body["data"])
    assert length(res.body["data"]) == 4
    assert Enum.all?(res.body["data"], &(&1["type"] == "article"))

    assert MapSet.new(H.ids(res.body)) ==
             MapSet.new([
               article(:elixir_basics),
               article(:otp_supervisors),
               article(:web_drafts),
               article(:archived_notes)
             ])
  end

  test "T02 responses are served as application/vnd.api+json with a jsonapi version member" do
    res = H.request(:get, "/api/articles")

    assert res.status == 200, inspect(res)
    assert res.content_type == @jsonapi
    assert res.body["jsonapi"] == %{"version" => "1.0"}
    assert res.body["links"]["self"] == "http://www.example.com/api/articles"
  end

  test "T03 article attributes contain exactly the public non-aggregate fields" do
    res = H.request(:get, "/api/articles/#{article(:elixir_basics)}")

    assert res.status == 200, inspect(res)

    assert MapSet.new(Map.keys(res.body["data"]["attributes"])) ==
             MapSet.new(~w(title slug body status rank word_count author_id))

    assert res.body["data"]["attributes"]["title"] == "Elixir Basics"
    assert res.body["data"]["attributes"]["status"] == "published"
    assert res.body["data"]["attributes"]["rank"] == 30
  end

  test "T04 author linkage is always rendered even without an include parameter" do
    res = H.request(:get, "/api/articles/#{article(:elixir_basics)}")

    assert res.status == 200, inspect(res)

    assert res.body["data"]["relationships"]["author"]["data"] == %{
             "type" => "author",
             "id" => author(:ada)
           }

    refute Map.has_key?(res.body["data"]["relationships"]["tags"], "data")
    refute Map.has_key?(res.body["data"]["relationships"]["comments"], "data")
  end

  test "T05 primary related and relationship routes generate links on the resource object" do
    id = article(:elixir_basics)
    res = H.request(:get, "/api/articles/#{id}")

    assert res.status == 200, inspect(res)

    assert res.body["data"]["links"]["self"] == "http://www.example.com/api/articles/#{id}"

    assert res.body["data"]["relationships"]["comments"]["links"]["related"] ==
             "http://www.example.com/api/articles/#{id}/comments"

    assert res.body["data"]["relationships"]["tags"]["links"]["self"] ==
             "http://www.example.com/api/articles/#{id}/relationships/tags"
  end

  test "T06 sparse fieldsets restrict attributes and can select the comment_count aggregate" do
    res =
      H.request(:get, "/api/articles/#{article(:elixir_basics)}?fields[article]=title,comment_count")

    assert res.status == 200, inspect(res)

    assert res.body["data"]["attributes"] == %{
             "title" => "Elixir Basics",
             "comment_count" => 2
           }
  end

  test "T07 sort supports descending order with a leading dash" do
    res = H.request(:get, "/api/articles?sort=-rank")

    assert res.status == 200, inspect(res)

    assert H.slugs(res.body) == [
             "archived-notes",
             "elixir-basics",
             "otp-supervisors",
             "web-drafts"
           ]

    asc = H.request(:get, "/api/articles?sort=rank")
    assert H.slugs(asc.body) == ["web-drafts", "otp-supervisors", "elixir-basics", "archived-notes"]
  end

  test "T08 an unknown sort field is rejected with invalid_sort" do
    res = H.request(:get, "/api/articles?sort=nope")

    assert res.status == 400, inspect(res)
    error = H.first_error(res.body)
    assert error["code"] == "invalid_sort"
    assert error["status"] == "400"
    assert error["source"]["parameter"] == "sort"
  end

  test "T09 filtering by a scalar attribute narrows the collection" do
    res = H.request(:get, "/api/articles?filter[status]=published&sort=rank")

    assert res.status == 200, inspect(res)
    assert H.slugs(res.body) == ["otp-supervisors", "elixir-basics"]
  end

  test "T10 filtering across a relationship path works" do
    res = H.request(:get, "/api/articles?filter[author][handle]=ada&sort=rank")

    assert res.status == 200, inspect(res)
    assert H.slugs(res.body) == ["otp-supervisors", "elixir-basics"]
  end

  test "T11 filtering with a comparison operator works" do
    res = H.request(:get, "/api/articles?filter[word_count][greater_than]=500&sort=rank")

    assert res.status == 200, inspect(res)
    assert H.slugs(res.body) == ["otp-supervisors", "elixir-basics"]
  end

  test "T12 filtering on an unknown field is rejected with a 400" do
    res = H.request(:get, "/api/articles?filter[nope]=1")

    assert res.status == 400, inspect(res)
    assert is_list(res.body["errors"])
  end

  test "T13 include=tags renders the tag resources in the included member" do
    res = H.request(:get, "/api/articles?include=tags")

    assert res.status == 200, inspect(res)

    included = res.body["included"] || []
    assert Enum.all?(included, &(&1["type"] == "tag"))

    assert MapSet.new(Enum.map(included, & &1["id"])) ==
             MapSet.new([tag(:elixir), tag(:otp), tag(:web)])

    elixir_basics =
      Enum.find(res.body["data"], &(&1["id"] == article(:elixir_basics)))

    assert MapSet.new(Enum.map(elixir_basics["relationships"]["tags"]["data"], & &1["id"])) ==
             MapSet.new([tag(:elixir), tag(:otp)])
  end

  test "T14 a multi hop include path is accepted and renders both hops" do
    res = H.request(:get, "/api/articles/#{article(:elixir_basics)}?include=author.articles")

    assert res.status == 200, inspect(res)

    included = res.body["included"] || []
    types = included |> Enum.map(& &1["type"]) |> MapSet.new()
    assert types == MapSet.new(["author", "article"])

    assert Enum.any?(included, &(&1["type"] == "author" and &1["id"] == author(:ada)))
    assert Enum.any?(included, &(&1["type"] == "article" and &1["id"] == article(:otp_supervisors)))
  end

  test "T15 an undeclared include path is rejected with invalid_includes" do
    res = H.request(:get, "/api/articles?include=nope")

    assert res.status == 400, inspect(res)
    error = H.first_error(res.body)
    assert error["code"] == "invalid_includes"
    assert error["source"]["parameter"] == "include"
  end

  test "T16 the article index paginates by offset and advertises a next link" do
    res = H.request(:get, "/api/articles?sort=rank&page[limit]=2")

    assert res.status == 200, inspect(res)
    assert H.slugs(res.body) == ["web-drafts", "otp-supervisors"]
    assert res.body["meta"]["page"] == %{"limit" => 2, "offset" => 0}
    assert res.body["links"]["prev"] == nil
    assert is_binary(res.body["links"]["next"])
    assert String.contains?(res.body["links"]["next"], "page[offset]=2")
  end

  test "T17 following the offset next link returns the remaining articles" do
    first = H.request(:get, "/api/articles?sort=rank&page[limit]=2")
    assert first.status == 200, inspect(first)

    second = H.follow(first.body["links"]["next"])

    assert second.status == 200, inspect(second)
    assert H.slugs(second.body) == ["elixir-basics", "archived-notes"]
    assert second.body["meta"]["page"] == %{"limit" => 2, "offset" => 2}
  end

  test "T18 the feed route is keyset paginated and defaults to two rank-descending articles" do
    res = H.request(:get, "/api/feed")

    assert res.status == 200, inspect(res)
    assert H.slugs(res.body) == ["archived-notes", "elixir-basics"]
    assert res.body["meta"]["page"] == %{"limit" => 2}
    assert is_binary(res.body["links"]["next"])
    assert String.contains?(res.body["links"]["next"], "page[after]=")
  end

  test "T19 following the feed cursor returns the last page and stops" do
    first = H.request(:get, "/api/feed")
    assert first.status == 200, inspect(first)

    second = H.follow(first.body["links"]["next"])

    assert second.status == 200, inspect(second)
    assert H.slugs(second.body) == ["otp-supervisors", "web-drafts"]
    assert second.body["links"]["next"] == nil
  end

  test "T20 a corrupt keyset cursor is rejected with invalid_keyset" do
    res = H.request(:get, "/api/feed?page[after]=not-a-cursor")

    assert res.status == 400, inspect(res)
    assert H.first_error(res.body)["code"] == "invalid_keyset"
  end

  test "T21 the feed route respects an explicit page limit" do
    res = H.request(:get, "/api/feed?page[limit]=3")

    assert res.status == 200, inspect(res)
    assert H.slugs(res.body) == ["archived-notes", "elixir-basics", "otp-supervisors"]
    assert res.body["meta"]["page"] == %{"limit" => 3}
  end

  test "T22 fetching an unknown article id returns a 404 not_found document" do
    res = H.request(:get, "/api/articles/00000000-0000-0000-0000-000000000000")

    assert res.status == 404, inspect(res)
    error = H.first_error(res.body)
    assert error["code"] == "not_found"
    assert error["status"] == "404"
  end

  test "T23 the tag collection ignores filter and sort query parameters" do
    res = H.request(:get, "/api/tags?filter[slug]=otp&sort=slug")

    assert res.status == 200, inspect(res)
    assert length(res.body["data"]) == 3

    assert MapSet.new(Enum.map(res.body["data"], &get_in(&1, ["attributes", "slug"]))) ==
             MapSet.new(["elixir", "otp", "web"])
  end

  test "T24 an editor can create an article and it is persisted" do
    res =
      H.request(:post, "/api/articles",
        actor: "ada",
        body: %{
          "data" => %{
            "type" => "article",
            "attributes" => %{
              "title" => "Streams",
              "slug" => "streams",
              "body" => "Lazy enumerables.",
              "word_count" => 640,
              "author_id" => author(:ada)
            }
          }
        }
      )

    assert res.status == 201, inspect(res)
    assert res.body["data"]["type"] == "article"
    assert res.body["data"]["attributes"]["slug"] == "streams"
    assert res.body["data"]["attributes"]["status"] == "draft"
    assert res.body["data"]["attributes"]["rank"] == 0

    listed = H.request(:get, "/api/articles")
    assert length(listed.body["data"]) == 5
  end

  test "T25 a missing required attribute produces a Required error with a source pointer" do
    res =
      H.request(:post, "/api/articles",
        actor: "ada",
        body: %{
          "data" => %{
            "type" => "article",
            "attributes" => %{"slug" => "no-title", "author_id" => author(:ada)}
          }
        }
      )

    assert res.status == 400, inspect(res)
    error = H.first_error(res.body)
    assert error["code"] == "required"
    assert error["title"] == "Required"
    assert error["source"]["pointer"] == "/data/attributes/title"
  end

  test "T26 a constraint violation produces invalid_attribute with the offending pointer" do
    res =
      H.request(:post, "/api/articles",
        actor: "ada",
        body: %{
          "data" => %{
            "type" => "article",
            "attributes" => %{"title" => "ab", "slug" => "ab", "author_id" => author(:ada)}
          }
        }
      )

    assert res.status == 400, inspect(res)
    error = H.first_error(res.body)
    assert error["code"] == "invalid_attribute"
    assert error["source"]["pointer"] == "/data/attributes/title"
    assert error["meta"]["min"] == 3
  end

  test "T27 an attribute that is not accepted produces invalid_body" do
    res =
      H.request(:post, "/api/articles",
        actor: "ada",
        body: %{
          "data" => %{
            "type" => "article",
            "attributes" => %{
              "title" => "Nope",
              "slug" => "nope",
              "author_id" => author(:ada),
              "bogus" => 1
            }
          }
        }
      )

    assert res.status == 400, inspect(res)
    error = H.first_error(res.body)
    assert error["code"] == "invalid_body"
    assert error["source"]["pointer"] == "/data/attributes/bogus"
  end

  test "T28 a create body without data.type is rejected with missing_type" do
    res =
      H.request(:post, "/api/articles",
        actor: "ada",
        body: %{
          "data" => %{
            "attributes" => %{"title" => "Typeless", "slug" => "typeless", "author_id" => author(:ada)}
          }
        }
      )

    assert res.status == 400, inspect(res)
    error = H.first_error(res.body)
    assert error["code"] == "missing_type"
    assert error["source"]["pointer"] == "/data"
  end

  test "T29 creating an article is forbidden for readers and anonymous callers" do
    body = %{
      "data" => %{
        "type" => "article",
        "attributes" => %{"title" => "Denied", "slug" => "denied", "author_id" => author(:ada)}
      }
    }

    reader = H.request(:post, "/api/articles", actor: "bob", body: body)
    assert reader.status == 403, inspect(reader)
    assert H.first_error(reader.body)["code"] == "forbidden"

    anonymous = H.request(:post, "/api/articles", body: body)
    assert anonymous.status == 403, inspect(anonymous)
    assert H.first_error(anonymous.body)["code"] == "forbidden"

    listed = H.request(:get, "/api/articles")
    assert length(listed.body["data"]) == 4
  end

  test "T30 patching an article updates its attributes" do
    id = article(:web_drafts)

    res =
      H.request(:patch, "/api/articles/#{id}",
        actor: "ada",
        body: %{
          "data" => %{
            "type" => "article",
            "id" => id,
            "attributes" => %{"title" => "Web Drafts v2", "rank" => 55}
          }
        }
      )

    assert res.status == 200, inspect(res)
    assert res.body["data"]["attributes"]["title"] == "Web Drafts v2"
    assert res.body["data"]["attributes"]["rank"] == 55

    again = H.request(:get, "/api/articles/#{id}")
    assert again.body["data"]["attributes"]["title"] == "Web Drafts v2"
  end

  test "T31 patching an article can replace its tags through data.relationships" do
    id = article(:elixir_basics)

    res =
      H.request(:patch, "/api/articles/#{id}",
        actor: "ada",
        body: %{
          "data" => %{
            "type" => "article",
            "id" => id,
            "attributes" => %{},
            "relationships" => %{
              "tags" => %{"data" => [%{"type" => "tag", "id" => tag(:web)}]}
            }
          }
        }
      )

    assert res.status == 200, inspect(res)

    linkage = H.request(:get, "/api/articles/#{id}/relationships/tags")
    assert linkage.status == 200, inspect(linkage)
    assert H.ids(linkage.body) == [tag(:web)]
  end

  test "T32 the publish route promotes a draft article" do
    id = article(:web_drafts)

    res =
      H.request(:patch, "/api/articles/#{id}/publish",
        actor: "ada",
        body: %{"data" => %{"type" => "article", "id" => id, "attributes" => %{}}}
      )

    assert res.status == 200, inspect(res)
    assert res.body["data"]["attributes"]["status"] == "published"

    again = H.request(:get, "/api/articles/#{id}")
    assert again.body["data"]["attributes"]["status"] == "published"
  end

  test "T33 the publish route refuses an archived article with the documented message" do
    id = article(:archived_notes)

    res =
      H.request(:patch, "/api/articles/#{id}/publish",
        actor: "ada",
        body: %{"data" => %{"type" => "article", "id" => id, "attributes" => %{}}}
      )

    assert res.status == 400, inspect(res)
    error = H.first_error(res.body)
    assert error["code"] == "invalid_attribute"
    assert error["detail"] == "cannot publish an archived article"
    assert error["source"]["pointer"] == "/data/attributes/status"

    again = H.request(:get, "/api/articles/#{id}")
    assert again.body["data"]["attributes"]["status"] == "archived"
  end

  test "T34 delete removes an article for editors and is forbidden for readers" do
    id = article(:archived_notes)

    denied = H.request(:delete, "/api/articles/#{id}", actor: "bob")
    assert denied.status == 403, inspect(denied)

    ok = H.request(:delete, "/api/articles/#{id}", actor: "ada")
    assert ok.status == 200, inspect(ok)
    assert ok.body["data"]["id"] == id

    gone = H.request(:get, "/api/articles/#{id}")
    assert gone.status == 404, inspect(gone)
  end

  test "T35 the related comments route returns full comment resources" do
    res = H.request(:get, "/api/articles/#{article(:elixir_basics)}/comments")

    assert res.status == 200, inspect(res)
    assert Enum.all?(res.body["data"], &(&1["type"] == "comment"))

    assert MapSet.new(H.ids(res.body)) ==
             MapSet.new([comment(:first), comment(:second)])

    assert Enum.all?(res.body["data"], &Map.has_key?(&1, "attributes"))
  end

  test "T36 the relationship route returns bare resource identifier objects" do
    res = H.request(:get, "/api/articles/#{article(:elixir_basics)}/relationships/tags")

    assert res.status == 200, inspect(res)

    assert MapSet.new(H.ids(res.body)) == MapSet.new([tag(:elixir), tag(:otp)])
    assert Enum.all?(res.body["data"], &(Map.keys(&1) |> Enum.sort() == ["id", "type"]))
    assert Enum.all?(res.body["data"], &(&1["type"] == "tag"))
  end

  test "T37 posting to the tags relationship appends linkage" do
    id = article(:otp_supervisors)

    res =
      H.request(:post, "/api/articles/#{id}/relationships/tags",
        actor: "ada",
        body: %{"data" => [%{"type" => "tag", "id" => tag(:web)}]}
      )

    assert res.status == 200, inspect(res)
    assert MapSet.new(H.ids(res.body)) == MapSet.new([tag(:otp), tag(:web)])

    linkage = H.request(:get, "/api/articles/#{id}/relationships/tags")
    assert MapSet.new(H.ids(linkage.body)) == MapSet.new([tag(:otp), tag(:web)])
  end

  test "T38 patching the tags relationship replaces linkage" do
    id = article(:elixir_basics)

    res =
      H.request(:patch, "/api/articles/#{id}/relationships/tags",
        actor: "ada",
        body: %{"data" => [%{"type" => "tag", "id" => tag(:web)}]}
      )

    assert res.status == 200, inspect(res)
    assert H.ids(res.body) == [tag(:web)]

    linkage = H.request(:get, "/api/articles/#{id}/relationships/tags")
    assert H.ids(linkage.body) == [tag(:web)]
  end

  test "T39 deleting from the tags relationship removes only the supplied members" do
    id = article(:elixir_basics)

    res =
      H.request(:delete, "/api/articles/#{id}/relationships/tags",
        actor: "ada",
        body: %{"data" => [%{"type" => "tag", "id" => tag(:otp)}]}
      )

    assert res.status == 200, inspect(res)
    assert H.ids(res.body) == [tag(:elixir)]

    linkage = H.request(:get, "/api/articles/#{id}/relationships/tags")
    assert H.ids(linkage.body) == [tag(:elixir)]
  end

  test "T40 relationship mutations reject malformed payloads, unknown ids and readers" do
    id = article(:elixir_basics)

    malformed =
      H.request(:post, "/api/articles/#{id}/relationships/tags",
        actor: "ada",
        body: %{"data" => %{"type" => "tag", "id" => tag(:web)}}
      )

    assert malformed.status == 400, inspect(malformed)
    assert H.first_error(malformed.body)["code"] == "invalid_body"
    assert H.first_error(malformed.body)["source"]["pointer"] == "/data"

    unknown =
      H.request(:post, "/api/articles/#{id}/relationships/tags",
        actor: "ada",
        body: %{"data" => [%{"type" => "tag", "id" => "00000000-0000-0000-0000-000000000000"}]}
      )

    assert unknown.status == 404, inspect(unknown)
    assert H.first_error(unknown.body)["code"] == "not_found"

    denied =
      H.request(:patch, "/api/articles/#{id}/relationships/tags",
        actor: "bob",
        body: %{"data" => [%{"type" => "tag", "id" => tag(:web)}]}
      )

    assert denied.status == 403, inspect(denied)
  end

  test "T41 the reindex generic action route returns the exact tally document" do
    res = H.request(:post, "/api/articles/reindex", actor: "cleo", body: %{})

    assert res.status == 201, inspect(res)
    assert res.body == %{"indexed" => 4, "published" => 2, "words" => 2350}
  end

  test "T42 the reindex route is restricted to admin actors" do
    editor = H.request(:post, "/api/articles/reindex", actor: "ada", body: %{})
    assert editor.status == 403, inspect(editor)
    assert H.first_error(editor.body)["code"] == "forbidden"

    anonymous = H.request(:post, "/api/articles/reindex", body: %{})
    assert anonymous.status == 403, inspect(anonymous)
  end

  test "T43 the tally route wraps its result and validates its arguments" do
    ok = H.request(:get, "/api/articles/tally/published")
    assert ok.status == 200, inspect(ok)
    assert ok.body == %{"result" => 2}

    draft = H.request(:get, "/api/articles/tally/draft")
    assert draft.body == %{"result" => 1}

    conflict = H.request(:get, "/api/articles/tally/published?status=draft")
    assert conflict.status == 400, inspect(conflict)
    assert H.first_error(conflict.body)["code"] == "invalid_query"

    invalid = H.request(:get, "/api/articles/tally/nope")
    assert invalid.status == 400, inspect(invalid)
    assert H.first_error(invalid.body)["code"] == "invalid_argument"
    assert H.first_error(invalid.body)["source"]["pointer"] == "/data/attributes/status"
  end

  test "T44 the moderation base route lists pending comments" do
    res = H.request(:get, "/api/moderation/comments/pending")

    assert res.status == 200, inspect(res)
    assert MapSet.new(H.ids(res.body)) == MapSet.new([comment(:second), comment(:third)])
  end

  test "T45 the moderation approve route approves a comment and is restricted" do
    id = comment(:second)

    denied =
      H.request(:patch, "/api/moderation/comments/#{id}/approve",
        actor: "bob",
        body: %{"data" => %{"type" => "comment", "id" => id, "attributes" => %{}}}
      )

    assert denied.status == 403, inspect(denied)

    ok =
      H.request(:patch, "/api/moderation/comments/#{id}/approve",
        actor: "ada",
        body: %{"data" => %{"type" => "comment", "id" => id, "attributes" => %{}}}
      )

    assert ok.status == 200, inspect(ok)
    assert ok.body["data"]["attributes"]["approved"] == true

    pending = H.request(:get, "/api/moderation/comments/pending")
    assert H.ids(pending.body) == [comment(:third)]
  end

  test "T46 the author related-articles route returns that author's articles" do
    res = H.request(:get, "/api/authors/#{author(:ada)}/articles?sort=rank")

    assert res.status == 200, inspect(res)
    assert H.slugs(res.body) == ["otp-supervisors", "elixir-basics"]
    assert Enum.all?(res.body["data"], &(&1["type"] == "article"))
  end

  test "T47 anyone may create a comment through the comment collection" do
    res =
      H.request(:post, "/api/comments",
        body: %{
          "data" => %{
            "type" => "comment",
            "attributes" => %{"body" => "Drive by", "article_id" => article(:otp_supervisors)}
          }
        }
      )

    assert res.status == 201, inspect(res)
    assert res.body["data"]["attributes"]["approved"] == false

    listed = H.request(:get, "/api/comments")
    assert length(listed.body["data"]) == 4
  end

  test "T48 an unknown actor handle is rejected with a 401 error document" do
    res = H.request(:get, "/api/articles", actor: "nobody")

    assert res.status == 401, inspect(res)

    assert res.body == %{
             "errors" => [
               %{
                 "code" => "unknown_actor",
                 "status" => "401",
                 "title" => "Unauthorized",
                 "detail" => "unknown actor handle nobody"
               }
             ]
           }
  end

  test "T49 content negotiation rejects unusable accept and content-type headers" do
    unacceptable =
      H.request(:get, "/api/articles", accept: "application/vnd.api+json; charset=utf-8")

    assert unacceptable.status == 406, inspect(unacceptable)
    assert H.first_error(unacceptable.body)["code"] == "unacceptable_media_type"

    unsupported =
      H.request(:post, "/api/articles",
        actor: "ada",
        content_type: "application/json",
        body: %{
          "data" => %{
            "type" => "article",
            "attributes" => %{"title" => "Nope", "slug" => "nope", "author_id" => author(:ada)}
          }
        }
      )

    assert unsupported.status == 415, inspect(unsupported)
    assert H.first_error(unsupported.body)["code"] == "unsupported_media_type"
  end

  test "T50 unmatched paths inside and outside the api prefix return distinct 404 documents" do
    inside = H.request(:get, "/api/nothing-here")
    assert inside.status == 404, inspect(inside)
    assert H.first_error(inside.body)["code"] == "no_route_found"

    outside = H.request(:get, "/nothing-here")
    assert outside.status == 404, inspect(outside)

    assert outside.body == %{
             "errors" => [
               %{
                 "code" => "not_found",
                 "status" => "404",
                 "title" => "NotFound",
                 "detail" => "no route found"
               }
             ]
           }
  end

  test "T51 the open api document is served and describes every route" do
    res = H.request(:get, "/api/open_api")

    assert res.status == 200, inspect(res)
    assert res.body["openapi"] == "3.0.0"

    paths = Map.keys(res.body["paths"] || %{})

    for expected <- [
          "/api/articles",
          "/api/articles/{id}",
          "/api/articles/{id}/publish",
          "/api/articles/{id}/comments",
          "/api/articles/{id}/relationships/tags",
          "/api/articles/reindex",
          "/api/articles/tally/{status}",
          "/api/feed",
          "/api/authors/{id}/articles",
          "/api/moderation/comments/pending",
          "/api/moderation/comments/{id}/approve"
        ] do
      assert expected in paths, "missing #{expected} in #{inspect(Enum.sort(paths))}"
    end
  end

  test "T52 the json schema document is served" do
    res = H.request(:get, "/api/json_schema")

    assert res.status == 200, inspect(res)
    assert Map.has_key?(res.body, "links")
    assert Map.has_key?(res.body, "definitions")
  end
end

ExUnit.run()
"""


@pytest.fixture(scope="session")
def suite():
    """Run the ExUnit driver once and index its results by scenario id."""
    with open(SCRIPT_PATH, "w", encoding="utf-8") as handle:
        handle.write(HARBOR_SUITE_EXS.lstrip("\n"))

    env = dict(os.environ)
    env["MIX_ENV"] = "dev"
    env.setdefault("HEX_OFFLINE", "1")

    completed = subprocess.run(
        ["mix", "run", SCRIPT_PATH],
        cwd=PROJECT_DIR,
        capture_output=True,
        text=True,
        timeout=2400,
        env=env,
    )

    results = {}
    for line in completed.stdout.splitlines():
        if not line.startswith(MARKER):
            continue
        parts = line.split("@@")
        if len(parts) < 5:
            continue
        name, status, encoded = parts[2], parts[3], parts[4]
        match = re.match(r"test (T\d+)", name)
        if not match:
            continue
        try:
            detail = base64.b64decode(encoded).decode("utf-8", errors="replace")
        except Exception:  # pragma: no cover - defensive
            detail = encoded
        results[match.group(1)] = (status, name, detail)

    noise = "\n".join(
        line for line in completed.stdout.splitlines() if not line.startswith(MARKER)
    )
    diagnostics = (
        f"exit code: {completed.returncode}\n"
        f"stdout (last 8000 chars):\n{noise[-8000:]}\n"
        f"stderr (last 8000 chars):\n{completed.stderr[-8000:]}"
    )

    print(diagnostics)
    return {"results": results, "diagnostics": diagnostics}


def _check(suite, scenario_id):
    results = suite["results"]
    if scenario_id not in results:
        raise AssertionError(
            f"Scenario {scenario_id} produced no result. The ExUnit driver did not run it "
            f"(most likely the project failed to compile).\n{suite['diagnostics']}"
        )
    status, name, detail = results[scenario_id]
    assert status == "passed", f"{name} did not pass ({status}):\n{detail}"


def test_t01_index_route_returns_every_fixture_article_as_a_json_api_resource_object(suite):
    _check(suite, "T01")

def test_t02_responses_are_served_as_application_vnd_api_json_with_a_jsonapi_version_member(suite):
    _check(suite, "T02")

def test_t03_article_attributes_contain_exactly_the_public_non_aggregate_fields(suite):
    _check(suite, "T03")

def test_t04_author_linkage_is_always_rendered_even_without_an_include_parameter(suite):
    _check(suite, "T04")

def test_t05_primary_related_and_relationship_routes_generate_links_on_the_resource_object(suite):
    _check(suite, "T05")

def test_t06_sparse_fieldsets_restrict_attributes_and_can_select_the_comment_count_aggregate(suite):
    _check(suite, "T06")

def test_t07_sort_supports_descending_order_with_a_leading_dash(suite):
    _check(suite, "T07")

def test_t08_an_unknown_sort_field_is_rejected_with_invalid_sort(suite):
    _check(suite, "T08")

def test_t09_filtering_by_a_scalar_attribute_narrows_the_collection(suite):
    _check(suite, "T09")

def test_t10_filtering_across_a_relationship_path_works(suite):
    _check(suite, "T10")

def test_t11_filtering_with_a_comparison_operator_works(suite):
    _check(suite, "T11")

def test_t12_filtering_on_an_unknown_field_is_rejected_with_a_400(suite):
    _check(suite, "T12")

def test_t13_include_tags_renders_the_tag_resources_in_the_included_member(suite):
    _check(suite, "T13")

def test_t14_a_multi_hop_include_path_is_accepted_and_renders_both_hops(suite):
    _check(suite, "T14")

def test_t15_an_undeclared_include_path_is_rejected_with_invalid_includes(suite):
    _check(suite, "T15")

def test_t16_the_article_index_paginates_by_offset_and_advertises_a_next_link(suite):
    _check(suite, "T16")

def test_t17_following_the_offset_next_link_returns_the_remaining_articles(suite):
    _check(suite, "T17")

def test_t18_the_feed_route_is_keyset_paginated_and_defaults_to_two_rank_descending_articles(suite):
    _check(suite, "T18")

def test_t19_following_the_feed_cursor_returns_the_last_page_and_stops(suite):
    _check(suite, "T19")

def test_t20_a_corrupt_keyset_cursor_is_rejected_with_invalid_keyset(suite):
    _check(suite, "T20")

def test_t21_the_feed_route_respects_an_explicit_page_limit(suite):
    _check(suite, "T21")

def test_t22_fetching_an_unknown_article_id_returns_a_404_not_found_document(suite):
    _check(suite, "T22")

def test_t23_the_tag_collection_ignores_filter_and_sort_query_parameters(suite):
    _check(suite, "T23")

def test_t24_an_editor_can_create_an_article_and_it_is_persisted(suite):
    _check(suite, "T24")

def test_t25_a_missing_required_attribute_produces_a_required_error_with_a_source_pointer(suite):
    _check(suite, "T25")

def test_t26_a_constraint_violation_produces_invalid_attribute_with_the_offending_pointer(suite):
    _check(suite, "T26")

def test_t27_an_attribute_that_is_not_accepted_produces_invalid_body(suite):
    _check(suite, "T27")

def test_t28_a_create_body_without_data_type_is_rejected_with_missing_type(suite):
    _check(suite, "T28")

def test_t29_creating_an_article_is_forbidden_for_readers_and_anonymous_callers(suite):
    _check(suite, "T29")

def test_t30_patching_an_article_updates_its_attributes(suite):
    _check(suite, "T30")

def test_t31_patching_an_article_can_replace_its_tags_through_data_relationships(suite):
    _check(suite, "T31")

def test_t32_the_publish_route_promotes_a_draft_article(suite):
    _check(suite, "T32")

def test_t33_the_publish_route_refuses_an_archived_article_with_the_documented_message(suite):
    _check(suite, "T33")

def test_t34_delete_removes_an_article_for_editors_and_is_forbidden_for_readers(suite):
    _check(suite, "T34")

def test_t35_the_related_comments_route_returns_full_comment_resources(suite):
    _check(suite, "T35")

def test_t36_the_relationship_route_returns_bare_resource_identifier_objects(suite):
    _check(suite, "T36")

def test_t37_posting_to_the_tags_relationship_appends_linkage(suite):
    _check(suite, "T37")

def test_t38_patching_the_tags_relationship_replaces_linkage(suite):
    _check(suite, "T38")

def test_t39_deleting_from_the_tags_relationship_removes_only_the_supplied_members(suite):
    _check(suite, "T39")

def test_t40_relationship_mutations_reject_malformed_payloads_unknown_ids_and_readers(suite):
    _check(suite, "T40")

def test_t41_the_reindex_generic_action_route_returns_the_exact_tally_document(suite):
    _check(suite, "T41")

def test_t42_the_reindex_route_is_restricted_to_admin_actors(suite):
    _check(suite, "T42")

def test_t43_the_tally_route_wraps_its_result_and_validates_its_arguments(suite):
    _check(suite, "T43")

def test_t44_the_moderation_base_route_lists_pending_comments(suite):
    _check(suite, "T44")

def test_t45_the_moderation_approve_route_approves_a_comment_and_is_restricted(suite):
    _check(suite, "T45")

def test_t46_the_author_related_articles_route_returns_that_author_s_articles(suite):
    _check(suite, "T46")

def test_t47_anyone_may_create_a_comment_through_the_comment_collection(suite):
    _check(suite, "T47")

def test_t48_an_unknown_actor_handle_is_rejected_with_a_401_error_document(suite):
    _check(suite, "T48")

def test_t49_content_negotiation_rejects_unusable_accept_and_content_type_headers(suite):
    _check(suite, "T49")

def test_t50_unmatched_paths_inside_and_outside_the_api_prefix_return_distinct_404_documents(suite):
    _check(suite, "T50")

def test_t51_the_open_api_document_is_served_and_describes_every_route(suite):
    _check(suite, "T51")

def test_t52_the_json_schema_document_is_served(suite):
    _check(suite, "T52")
