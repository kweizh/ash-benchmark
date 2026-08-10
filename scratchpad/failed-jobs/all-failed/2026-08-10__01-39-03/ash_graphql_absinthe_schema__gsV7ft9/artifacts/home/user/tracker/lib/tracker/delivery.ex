defmodule Tracker.Delivery do
  @moduledoc false
  use Ash.Domain, otp_app: :tracker, extensions: [AshGraphql.Domain]

  graphql do
    authorize? true
    show_raised_errors? true

    queries do
      get Tracker.Delivery.Ticket, :ticket, :read
      get Tracker.Delivery.Ticket, :ticket_or_fail, :read, allow_nil?: false
      read_one Tracker.Delivery.Ticket, :top_ticket, :top_severity
      list Tracker.Delivery.Ticket, :tickets, :read, relay?: true

      get Tracker.Delivery.Project, :project, :read
      list Tracker.Delivery.Project, :projects, :read, paginate_with: nil

      list Tracker.Delivery.Label, :labels, :read, paginate_with: nil

      list Tracker.Delivery.User, :users, :read, paginate_with: nil

      action Tracker.Delivery.Project, :audit_sprint, :audit_sprint
    end

    mutations do
      create Tracker.Delivery.Ticket, :create_ticket, :create,
        relay_id_translations: [input: [project_id: :project, assignee_id: :user]]

      update Tracker.Delivery.Ticket, :update_ticket, :update,
        relay_id_translations: [input: [assignee_id: :user]]

      destroy Tracker.Delivery.Ticket, :destroy_ticket, :destroy

      create Tracker.Delivery.Project, :create_project, :create
      update Tracker.Delivery.Project, :archive_project, :archive

      action Tracker.Delivery.Project, :freeze_sprint, :freeze_sprint,
        error_location: :in_result
    end
  end

  resources do
    resource Tracker.Delivery.User
    resource Tracker.Delivery.Project
    resource Tracker.Delivery.Ticket
    resource Tracker.Delivery.Label
    resource Tracker.Delivery.TicketLabel
  end
end
