defmodule Tracker.Delivery.Seed do
  @moduledoc false
  alias Tracker.Delivery.{Label, Project, Ticket, TicketLabel, User}

  def alice_id, do: "11111111-1111-1111-1111-111111111111"
  def bob_id, do: "22222222-2222-2222-2222-222222222222"
  def apollo_id, do: "aaaaaaaa-0000-0000-0000-000000000001"
  def zephyr_id, do: "aaaaaaaa-0000-0000-0000-000000000002"
  def bug_id, do: "bbbbbbbb-0000-0000-0000-000000000001"
  def ux_id, do: "bbbbbbbb-0000-0000-0000-000000000002"
  def perf_id, do: "bbbbbbbb-0000-0000-0000-000000000003"
  def ticket_id(n), do: "cccccccc-0000-0000-0000-00000000000#{n}"

  def seed! do
    Ash.Seed.seed!(User, %{
      id: alice_id(),
      email: "alice@example.com",
      display_name: "Alice",
      role: :admin,
      internal_notes: "founder"
    })

    Ash.Seed.seed!(User, %{
      id: bob_id(),
      email: "bob@example.com",
      display_name: "Bob",
      role: :member,
      internal_notes: "contractor"
    })

    Ash.Seed.seed!(Project, %{
      id: apollo_id(),
      name: "Apollo",
      slug: "apollo",
      archived: false
    })

    Ash.Seed.seed!(Project, %{
      id: zephyr_id(),
      name: "Zephyr",
      slug: "zephyr",
      archived: false
    })

    Ash.Seed.seed!(Label, %{id: bug_id(), name: "bug", colour: "#c0392b"})
    Ash.Seed.seed!(Label, %{id: ux_id(), name: "ux", colour: "#8e44ad"})
    Ash.Seed.seed!(Label, %{id: perf_id(), name: "perf", colour: "#16a085"})

    tickets = [
      %{
        id: ticket_id(1),
        title: "Login fails on Safari",
        status: :open,
        severity: 5,
        estimate_points: 3,
        sequence: 1,
        internal_reference: "APOLLO-1",
        project_id: apollo_id(),
        assignee_id: alice_id()
      },
      %{
        id: ticket_id(2),
        title: "Improve empty state",
        status: :in_progress,
        severity: 2,
        estimate_points: 5,
        sequence: 2,
        internal_reference: "APOLLO-2",
        project_id: apollo_id(),
        assignee_id: bob_id()
      },
      %{
        id: ticket_id(3),
        title: "Slow dashboard",
        status: :open,
        severity: 4,
        estimate_points: 8,
        sequence: 3,
        internal_reference: "APOLLO-3",
        project_id: apollo_id(),
        assignee_id: alice_id()
      },
      %{
        id: ticket_id(4),
        title: "Broken CSV export",
        status: :blocked,
        severity: 3,
        estimate_points: 2,
        sequence: 4,
        internal_reference: "APOLLO-4",
        project_id: apollo_id(),
        assignee_id: nil
      },
      %{
        id: ticket_id(5),
        title: "Update docs",
        status: :done,
        severity: 1,
        estimate_points: 1,
        sequence: 5,
        internal_reference: "APOLLO-5",
        project_id: apollo_id(),
        assignee_id: bob_id()
      },
      %{
        id: ticket_id(6),
        title: "Zephyr smoke test",
        status: :open,
        severity: 2,
        estimate_points: 13,
        sequence: 6,
        internal_reference: "ZEPHYR-1",
        project_id: zephyr_id(),
        assignee_id: nil
      }
    ]

    Enum.each(tickets, &Ash.Seed.seed!(Ticket, &1))

    join = fn ticket, label ->
      Ash.Seed.seed!(TicketLabel, %{ticket_id: ticket, label_id: label})
    end

    join.(ticket_id(1), bug_id())
    join.(ticket_id(2), ux_id())
    join.(ticket_id(3), bug_id())
    join.(ticket_id(3), perf_id())
    join.(ticket_id(5), ux_id())

    :ok
  end
end
