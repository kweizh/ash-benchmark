defmodule Kbapi.Knowledge.Fixtures do
  @moduledoc """
  Deterministic fixture data for the knowledge base.

  Do not modify this module. The verification suite calls `reset!/0` before every
  scenario and looks records up through the `*_id/1` helpers.
  """

  alias Kbapi.Knowledge.{Article, ArticleTag, Author, Comment, Tag}

  @authors %{
    ada: %{
      id: "11111111-1111-1111-1111-111111111101",
      name: "Ada Lovelace",
      handle: "ada",
      bio: "Writes about analytical engines.",
      role: :editor
    },
    bob: %{
      id: "11111111-1111-1111-1111-111111111102",
      name: "Bob Reader",
      handle: "bob",
      bio: nil,
      role: :reader
    },
    cleo: %{
      id: "11111111-1111-1111-1111-111111111103",
      name: "Cleo Root",
      handle: "cleo",
      bio: "Runs the knowledge base.",
      role: :admin
    }
  }

  @tags %{
    elixir: %{id: "22222222-2222-2222-2222-222222222201", name: "Elixir", slug: "elixir"},
    otp: %{id: "22222222-2222-2222-2222-222222222202", name: "OTP", slug: "otp"},
    web: %{id: "22222222-2222-2222-2222-222222222203", name: "Web", slug: "web"}
  }

  @articles %{
    elixir_basics: %{
      id: "33333333-3333-3333-3333-333333333301",
      title: "Elixir Basics",
      slug: "elixir-basics",
      body: "Pattern matching and pipes.",
      status: :published,
      rank: 30,
      word_count: 1200,
      author: :ada,
      tags: [:elixir, :otp]
    },
    otp_supervisors: %{
      id: "33333333-3333-3333-3333-333333333302",
      title: "OTP Supervisors",
      slug: "otp-supervisors",
      body: "Restart strategies explained.",
      status: :published,
      rank: 20,
      word_count: 800,
      author: :ada,
      tags: [:otp]
    },
    web_drafts: %{
      id: "33333333-3333-3333-3333-333333333303",
      title: "Web Drafts",
      slug: "web-drafts",
      body: nil,
      status: :draft,
      rank: 10,
      word_count: 300,
      author: :cleo,
      tags: [:web]
    },
    archived_notes: %{
      id: "33333333-3333-3333-3333-333333333304",
      title: "Archived Notes",
      slug: "archived-notes",
      body: "Old material.",
      status: :archived,
      rank: 40,
      word_count: 50,
      author: :bob,
      tags: []
    }
  }

  @comments %{
    first: %{
      id: "44444444-4444-4444-4444-444444444401",
      body: "First!",
      approved: true,
      article: :elixir_basics
    },
    second: %{
      id: "44444444-4444-4444-4444-444444444402",
      body: "Second thoughts.",
      approved: false,
      article: :elixir_basics
    },
    third: %{
      id: "44444444-4444-4444-4444-444444444403",
      body: "Nice write up.",
      approved: false,
      article: :otp_supervisors
    }
  }

  def author_id(key), do: @authors |> Map.fetch!(key) |> Map.fetch!(:id)
  def tag_id(key), do: @tags |> Map.fetch!(key) |> Map.fetch!(:id)
  def article_id(key), do: @articles |> Map.fetch!(key) |> Map.fetch!(:id)
  def comment_id(key), do: @comments |> Map.fetch!(key) |> Map.fetch!(:id)

  def reset! do
    Enum.each([Comment, ArticleTag, Article, Tag, Author], fn resource ->
      resource
      |> Ash.read!(authorize?: false)
      |> Enum.each(&Ash.destroy!(&1, authorize?: false))
    end)

    Enum.each(@authors, fn {_key, attrs} -> Ash.Seed.seed!(Author, attrs) end)
    Enum.each(@tags, fn {_key, attrs} -> Ash.Seed.seed!(Tag, attrs) end)

    Enum.each(@articles, fn {_key, attrs} ->
      Ash.Seed.seed!(Article, %{
        id: attrs.id,
        title: attrs.title,
        slug: attrs.slug,
        body: attrs.body,
        status: attrs.status,
        rank: attrs.rank,
        word_count: attrs.word_count,
        author_id: author_id(attrs.author)
      })

      Enum.each(attrs.tags, fn tag ->
        Ash.Seed.seed!(ArticleTag, %{article_id: attrs.id, tag_id: tag_id(tag)})
      end)
    end)

    Enum.each(@comments, fn {_key, attrs} ->
      Ash.Seed.seed!(Comment, %{
        id: attrs.id,
        body: attrs.body,
        approved: attrs.approved,
        article_id: article_id(attrs.article)
      })
    end)

    :ok
  end
end
