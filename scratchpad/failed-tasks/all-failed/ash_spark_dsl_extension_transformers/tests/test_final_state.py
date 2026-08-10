import base64
import os
import subprocess

import pytest

PROJECT_DIR = "/home/user/lifecycle"
SCRIPT_PATH = "/tmp/harbor_final_state.exs"
MARKER = "@@HARBOR@@"

SUITE_EXS = r'''
defmodule HarborFormatter do
  @moduledoc false
  use GenServer

  def init(_opts), do: {:ok, %{}}

  def handle_cast({:test_finished, test}, state) do
    {status, detail} =
      case test.state do
        nil ->
          {"pass", ""}

        {:failed, failures} ->
          {"fail",
           ExUnit.Formatter.format_test_failure(test, failures, 1, 120, fn _kind, msg -> msg end)}

        {:invalid, _} ->
          {"fail", "invalid: a setup block failed"}

        {:excluded, _} ->
          {"skip", ""}

        {:skipped, _} ->
          {"skip", ""}
      end

    IO.puts("@@HARBOR@@#{test.name}@@#{status}@@#{Base.encode64(detail)}")
    {:noreply, state}
  end

  def handle_cast(_event, state), do: {:noreply, state}
end

ExUnit.start(
  autorun: false,
  formatters: [HarborFormatter],
  seed: 0,
  colors: [enabled: false],
  max_failures: :infinity,
  timeout: 120_000
)

defmodule HarborSandbox do
  @moduledoc false
  use Ash.Domain, validate_config_inclusion?: false

  resources do
    allow_unregistered? true
  end
end

defmodule HarborFinalTest do
  use ExUnit.Case, async: false

  @archival Lifecycle.Archival
  @hooks Lifecycle.Archival.Hooks
  @info Lifecycle.Archival.Info
  @reason_struct Lifecycle.Archival.Reason
  @default_reason_struct Lifecycle.Archival.DefaultReason
  @hook_struct Lifecycle.Archival.Hook
  @document Lifecycle.Records.Document
  @contract Lifecycle.Records.Contract
  @event Lifecycle.Records.ArchivalEvent
  @stamp_note Lifecycle.Records.StampNote

  # ---------------------------------------------------------------- helpers

  defp section do
    sections = @archival.sections()
    assert length(sections) == 1, "expected exactly one top level section, got #{inspect(sections)}"
    hd(sections)
  end

  defp entity(name) do
    Enum.find(section().entities, &(&1.name == name)) ||
      flunk("no `#{name}` entity declared in the `archival` section")
  end

  defp audit_section do
    Enum.find(section().sections, &(&1.name == :audit)) ||
      flunk("no nested `audit` section declared inside `archival`")
  end

  defp opt(schema, key) do
    Keyword.get(schema, key) || flunk("option `#{key}` missing from schema #{inspect(schema)}")
  end

  defp resource_source(module_name, body, extensions \\ "Lifecycle.Archival", extra_attrs \\ "") do
    """
    defmodule Elixir.#{module_name} do
      use Ash.Resource,
        domain: HarborSandbox,
        data_layer: Ash.DataLayer.Ets,
        extensions: [#{extensions}]

      ets do
        private? true
      end

      attributes do
        uuid_primary_key :id
    #{extra_attrs}
      end

      actions do
        defaults [:read, :destroy, create: []]
      end

      archival do
    #{body}
      end
    end
    """
  end

  defp dsl_error_messages(source) do
    {_result, diagnostics} =
      Code.with_diagnostics(fn ->
        ExUnit.CaptureIO.capture_io(:stderr, fn -> Code.compile_string(source) end)
      end)

    diagnostics
    |> Enum.map(& &1.message)
    |> Enum.filter(&String.contains?(&1, "Spark.Error.DslError"))
  end

  defp assert_dsl_error(source, module_name, path_fragment, message) do
    messages = dsl_error_messages(source)

    assert messages != [],
           "expected compiling #{module_name} to report a Spark.Error.DslError, got none"

    joined = Enum.join(messages, "\n")

    assert String.contains?(joined, "[#{module_name}]"),
           "expected the DslError to carry module #{module_name}, got:\n#{joined}"

    assert String.contains?(joined, path_fragment),
           "expected the DslError path to render as `#{String.trim_trailing(path_fragment)}`, got:\n#{joined}"

    assert String.contains?(joined, message),
           "expected the DslError message `#{message}`, got:\n#{joined}"
  end

  defp compile_ok!(source) do
    messages = dsl_error_messages(source)

    assert messages == [],
           "expected a clean compile, but got DslErrors:\n#{Enum.join(messages, "\n")}"
  end

  defp constraints_one_of(%{constraints: constraints}), do: Keyword.get(constraints, :one_of)

  defp change_modules(action) do
    Enum.map(action.changes, fn %{change: change} ->
      case change do
        {module, _opts} -> module
        module -> module
      end
    end)
  end

  # -------------------------------------------------------- extension shape

  test "T01 the archival section is patchable, singleton-limited and correctly nested" do
    sec = section()
    assert sec.name == :archival, "expected the section to be named :archival"
    assert sec.patchable? == true, "the `archival` section must be patchable"

    assert sec.singleton_entity_keys == [:default_reason],
           "expected singleton_entity_keys [:default_reason], got #{inspect(sec.singleton_entity_keys)}"

    assert Enum.map(sec.entities, & &1.name) == [:reason, :default_reason],
           "expected entities [:reason, :default_reason], got #{inspect(Enum.map(sec.entities, & &1.name))}"

    assert Enum.map(sec.sections, & &1.name) == [:audit],
           "expected exactly one nested section :audit, got #{inspect(Enum.map(sec.sections, & &1.name))}"
  end

  test "T02 the archival section schema declares the three options with their defaults" do
    schema = section().schema

    assert opt(schema, :timestamp_attribute)[:type] == :atom
    assert opt(schema, :timestamp_attribute)[:default] == :archived_at
    assert opt(schema, :action_name)[:type] == :atom
    assert opt(schema, :action_name)[:default] == :archive
    assert opt(schema, :reason_required?)[:type] == :boolean
    assert opt(schema, :reason_required?)[:default] == false
  end

  test "T03 the nested audit section schema declares its three options with their defaults" do
    schema = audit_section().schema

    assert opt(schema, :enabled?)[:type] == :boolean
    assert opt(schema, :enabled?)[:default] == false
    assert opt(schema, :event_resource)[:type] == :module
    assert Keyword.fetch!(opt(schema, :event_resource), :default) == nil
    assert opt(schema, :relationship_name)[:type] == :atom
    assert opt(schema, :relationship_name)[:default] == :archival_events
  end

  test "T04 the reason entity declares target, args, identifier and schema defaults" do
    reason = entity(:reason)

    assert reason.target == @reason_struct,
           "expected the reason entity target #{inspect(@reason_struct)}, got #{inspect(reason.target)}"

    assert reason.args == [:name], "expected the reason entity args [:name]"
    assert reason.identifier == :name, "expected the reason entity to be identified by :name"

    schema = reason.schema
    assert opt(schema, :name)[:type] == :atom
    assert opt(schema, :name)[:required] == true
    assert opt(schema, :code)[:type] == :string
    assert opt(schema, :code)[:required] == true
    assert opt(schema, :retention_days)[:type] == :pos_integer
    assert opt(schema, :retention_days)[:default] == 30
    assert opt(schema, :terminal?)[:type] == :boolean
    assert opt(schema, :terminal?)[:default] == false
  end

  test "T05 the default_reason entity declares target and args" do
    default_reason = entity(:default_reason)

    assert default_reason.target == @default_reason_struct,
           "expected target #{inspect(@default_reason_struct)}, got #{inspect(default_reason.target)}"

    assert default_reason.args == [:name], "expected the default_reason entity args [:name]"
  end

  test "T06 the extension declares the three required transformers" do
    transformers = @archival.transformers()

    for expected <- [
          Lifecycle.Archival.Transformers.AddArchivalFields,
          Lifecycle.Archival.Transformers.AddArchivalActions,
          Lifecycle.Archival.Transformers.AddAuditRelationship
        ] do
      assert expected in transformers,
             "expected #{inspect(expected)} in Lifecycle.Archival.transformers/0, got #{inspect(transformers)}"
    end

    for transformer <- transformers do
      assert Code.ensure_loaded?(transformer) and function_exported?(transformer, :transform, 1),
             "#{inspect(transformer)} does not implement Spark.Dsl.Transformer"
    end
  end

  test "T07 the extension declares the archival verifier" do
    verifiers = @archival.verifiers()

    assert Lifecycle.Archival.Verifiers.VerifyArchival in verifiers,
           "expected Lifecycle.Archival.Verifiers.VerifyArchival in Lifecycle.Archival.verifiers/0, got #{inspect(verifiers)}"

    assert Code.ensure_loaded?(Lifecycle.Archival.Verifiers.VerifyArchival) and
             function_exported?(Lifecycle.Archival.Verifiers.VerifyArchival, :verify, 1),
           "Lifecycle.Archival.Verifiers.VerifyArchival does not implement Spark.Dsl.Verifier"
  end

  test "T08 the hooks extension patches a hook entity into the archival section" do
    patches = @hooks.dsl_patches()
    assert length(patches) == 1, "expected exactly one DSL patch, got #{inspect(patches)}"
    patch = hd(patches)

    assert is_struct(patch, Spark.Dsl.Patch.AddEntity),
           "expected a %Spark.Dsl.Patch.AddEntity{}, got #{inspect(patch)}"

    assert patch.section_path == [:archival],
           "expected the patch to target [:archival], got #{inspect(patch.section_path)}"

    assert patch.entity.name == :hook
    assert patch.entity.target == @hook_struct
    assert patch.entity.args == [:name]
    assert patch.entity.identifier == :name
    assert Keyword.get(patch.entity.schema, :module)[:required] == true

    assert @hooks.add_extensions() == [@archival],
           "expected Lifecycle.Archival.Hooks.add_extensions/0 to be [Lifecycle.Archival], got #{inspect(@hooks.add_extensions())}"
  end

  # ------------------------------------------------------------ info module

  test "T09 the generated timestamp_attribute getters return the configured value" do
    assert @info.archival_timestamp_attribute!(@document) == :archived_at
    assert @info.archival_timestamp_attribute!(@contract) == :retired_at
    assert @info.archival_timestamp_attribute(@contract) == {:ok, :retired_at}
  end

  test "T10 the generated action_name and reason_required? getters return the configured values" do
    assert @info.archival_action_name!(@document) == :archive
    assert @info.archival_action_name!(@contract) == :retire
    assert @info.archival_reason_required?(@document) == false
    assert @info.archival_reason_required?(@contract) == true
  end

  test "T11 the generated audit getters return the configured values" do
    assert @info.archival_audit_enabled?(@document) == false
    assert @info.archival_audit_enabled?(@contract) == true
    assert @info.archival_audit_event_resource!(@contract) == @event
    assert @info.archival_audit_event_resource(@contract) == {:ok, @event}
    assert @info.archival_audit_relationship_name!(@document) == :archival_events
    assert @info.archival_audit_relationship_name!(@contract) == :archival_events
  end

  test "T12 the generated options maps expose defaults for an unconfigured resource" do
    assert @info.archival_options(@document) == %{
             timestamp_attribute: :archived_at,
             action_name: :archive,
             reason_required?: false
           }

    assert @info.archival_audit_options(@document) == %{
             enabled?: false,
             relationship_name: :archival_events
           }
  end

  test "T13 archival_reasons/1 returns the declared reasons in declaration order" do
    doc = @info.archival_reasons(@document)
    assert length(doc) == 2, "expected two reasons on Document, got #{inspect(doc)}"

    assert Enum.map(doc, &{&1.name, &1.code, &1.retention_days, &1.terminal?}) == [
             {:maintenance, "MNT", 30, false},
             {:legal_hold, "LGL", 3650, true}
           ]

    assert Enum.all?(doc, &is_struct(&1, @reason_struct)),
           "expected %Lifecycle.Archival.Reason{} structs, got #{inspect(doc)}"

    assert Enum.map(@info.archival_reasons(@contract), &{&1.name, &1.code, &1.retention_days, &1.terminal?}) ==
             [{:breach, "BRC", 30, false}, {:expiry, "EXP", 365, false}]
  end

  test "T14 archival_default_reason/1 returns the declared default or nil" do
    default = @info.archival_default_reason(@document)

    assert is_struct(default, @default_reason_struct),
           "expected a %Lifecycle.Archival.DefaultReason{}, got #{inspect(default)}"

    assert default.name == :maintenance
    assert @info.archival_default_reason(@contract) == nil
  end

  test "T15 archival_hooks/1 returns the declared hooks" do
    hooks = @info.archival_hooks(@contract)
    assert length(hooks) == 1, "expected one hook on Contract, got #{inspect(hooks)}"
    hook = hd(hooks)
    assert is_struct(hook, @hook_struct), "expected a %Lifecycle.Archival.Hook{}"
    assert hook.name == :stamp_note
    assert hook.module == @stamp_note
    assert @info.archival_hooks(@document) == []
  end

  # ------------------------------------------------------- generated fields

  test "T16 the timestamp attribute is generated with the configured name and shape" do
    archived_at = Ash.Resource.Info.attribute(@document, :archived_at)
    assert archived_at, "Document is missing the generated :archived_at attribute"
    assert archived_at.type == Ash.Type.UtcDatetimeUsec
    assert archived_at.allow_nil? == true
    assert archived_at.public? == true
    assert archived_at.writable? == false

    retired_at = Ash.Resource.Info.attribute(@contract, :retired_at)
    assert retired_at, "Contract is missing the generated :retired_at attribute"
    assert retired_at.type == Ash.Type.UtcDatetimeUsec
    assert retired_at.allow_nil? == true
    assert retired_at.public? == true
    assert retired_at.writable? == false

    refute Ash.Resource.Info.attribute(@contract, :archived_at),
           "Contract must not have an :archived_at attribute, its timestamp attribute is :retired_at"
  end

  test "T17 the archival_reason attribute is generated with the declared reason names" do
    doc = Ash.Resource.Info.attribute(@document, :archival_reason)
    assert doc, "Document is missing the generated :archival_reason attribute"
    assert doc.type == Ash.Type.Atom
    assert doc.allow_nil? == true
    assert doc.public? == true
    assert doc.writable? == false
    assert constraints_one_of(doc) == [:maintenance, :legal_hold]

    contract = Ash.Resource.Info.attribute(@contract, :archival_reason)
    assert contract, "Contract is missing the generated :archival_reason attribute"
    assert constraints_one_of(contract) == [:breach, :expiry]
  end

  test "T18 the update action is generated with the configured name, empty accept and non-atomic" do
    archive = Ash.Resource.Info.action(@document, :archive)
    assert archive, "Document is missing the generated :archive action"
    assert archive.type == :update
    assert archive.accept == []
    assert archive.require_atomic? == false

    retire = Ash.Resource.Info.action(@contract, :retire)
    assert retire, "Contract is missing the generated :retire action"
    assert retire.type == :update
    assert retire.accept == []
    assert retire.require_atomic? == false
  end

  test "T19 the generated update action carries exactly one constrained :reason argument" do
    archive = Ash.Resource.Info.action(@document, :archive)
    assert length(archive.arguments) == 1, "expected one argument, got #{inspect(archive.arguments)}"
    argument = hd(archive.arguments)
    assert argument.name == :reason
    assert argument.type == Ash.Type.Atom
    assert argument.allow_nil? == true
    assert constraints_one_of(argument) == [:maintenance, :legal_hold]

    retire_argument = hd(Ash.Resource.Info.action(@contract, :retire).arguments)
    assert retire_argument.name == :reason
    assert retire_argument.allow_nil? == false
    assert constraints_one_of(retire_argument) == [:breach, :expiry]
  end

  test "T20 the archived and active read actions are generated on both resources" do
    for resource <- [@document, @contract], name <- [:archived, :active] do
      action = Ash.Resource.Info.action(resource, name)
      assert action, "#{inspect(resource)} is missing the generated :#{name} read action"
      assert action.type == :read
    end
  end

  test "T21 declared hooks are appended to the generated action's changes" do
    doc_changes = change_modules(Ash.Resource.Info.action(@document, :archive))

    assert length(doc_changes) == 1,
           "Document's :archive action should carry exactly one change, got #{inspect(doc_changes)}"

    contract_changes = change_modules(Ash.Resource.Info.action(@contract, :retire))

    assert length(contract_changes) == 2,
           "Contract's :retire action should carry exactly two changes, got #{inspect(contract_changes)}"

    assert List.last(contract_changes) == @stamp_note,
           "expected the hook module #{inspect(@stamp_note)} to be the last change, got #{inspect(contract_changes)}"

    refute @stamp_note in doc_changes,
           "Document declares no hooks, so #{inspect(@stamp_note)} must not appear in its changes"
  end

  test "T22 the audit relationship and aggregate are generated only when audit is enabled" do
    relationship = Ash.Resource.Info.relationship(@contract, :archival_events)
    assert relationship, "Contract is missing the generated :archival_events relationship"
    assert relationship.type == :has_many
    assert relationship.destination == @event
    assert relationship.destination_attribute == :subject_id
    assert relationship.source == @contract

    aggregate = Ash.Resource.Info.aggregate(@contract, :archival_event_count)
    assert aggregate, "Contract is missing the generated :archival_event_count aggregate"
    assert aggregate.kind == :count
    assert List.wrap(aggregate.relationship_path) == [:archival_events]

    refute Ash.Resource.Info.relationship(@document, :archival_events),
           "Document has audit disabled and must not gain an :archival_events relationship"

    refute Ash.Resource.Info.aggregate(@document, :archival_event_count),
           "Document has audit disabled and must not gain an :archival_event_count aggregate"
  end

  test "T23 the reason codes are persisted onto each host resource" do
    assert Spark.Dsl.Extension.get_persisted(@document, :archival_reason_codes) == %{
             maintenance: "MNT",
             legal_hold: "LGL"
           }

    assert Spark.Dsl.Extension.get_persisted(@contract, :archival_reason_codes) == %{
             breach: "BRC",
             expiry: "EXP"
           }
  end

  test "T24 the generated code interfaces are defined on the host resource modules" do
    assert function_exported?(@document, :archive!, 1),
           "expected Lifecycle.Records.Document.archive!/1 to be generated"

    assert function_exported?(@document, :archive!, 2),
           "expected the generated archive interface to take an optional positional reason"

    assert function_exported?(@document, :archived_records!, 0),
           "expected Lifecycle.Records.Document.archived_records!/0 to be generated"

    assert function_exported?(@contract, :retire!, 2),
           "expected Lifecycle.Records.Contract.retire!/2 to be generated"

    assert function_exported?(@contract, :archived_records!, 0),
           "expected Lifecycle.Records.Contract.archived_records!/0 to be generated"
  end

  test "T25 listing only the hooks extension also activates the archival extension" do
    extensions = Spark.Dsl.Extension.get_persisted(@contract, :extensions)

    assert @hooks in extensions,
           "expected Lifecycle.Archival.Hooks in Contract's extensions, got #{inspect(extensions)}"

    assert @archival in extensions,
           "expected Lifecycle.Archival to be pulled in by the hooks extension, got #{inspect(extensions)}"
  end

  # ----------------------------------------------------------------- runtime

  test "T26 archiving without a reason falls back to the declared default_reason" do
    document = Ash.create!(@document, %{title: "d1"}, action: :open)
    assert document.archived_at == nil
    archived = Ash.update!(document, %{}, action: :archive)
    assert archived.archived_at != nil, "the archive action must stamp :archived_at"
    assert archived.archival_reason == :maintenance
  end

  test "T27 archiving with an explicit reason records that reason" do
    document = Ash.create!(@document, %{title: "d2"}, action: :open)
    archived = Ash.update!(document, %{reason: :legal_hold}, action: :archive)
    assert archived.archival_reason == :legal_hold
    assert archived.archived_at != nil
  end

  test "T28 an undeclared reason is rejected by the generated argument constraints" do
    document = Ash.create!(@document, %{title: "d3"}, action: :open)

    assert {:error, %Ash.Error.Invalid{errors: errors}} =
             Ash.update(document, %{reason: :nope}, action: :archive)

    assert Enum.any?(errors, fn error ->
             is_struct(error, Ash.Error.Changes.InvalidArgument) and error.field == :reason
           end),
           "expected an Ash.Error.Changes.InvalidArgument on :reason, got #{inspect(errors)}"
  end

  test "T29 the generated update action accepts no attribute input" do
    document = Ash.create!(@document, %{title: "d4"}, action: :open)

    assert {:error, %Ash.Error.Invalid{errors: title_errors}} =
             Ash.update(document, %{title: "renamed"}, action: :archive)

    assert Enum.any?(title_errors, &is_struct(&1, Ash.Error.Invalid.NoSuchInput)),
           "expected NoSuchInput for :title, got #{inspect(title_errors)}"

    assert {:error, %Ash.Error.Invalid{errors: stamp_errors}} =
             Ash.update(document, %{archived_at: DateTime.utc_now()}, action: :archive)

    assert Enum.any?(stamp_errors, &is_struct(&1, Ash.Error.Invalid.NoSuchInput)),
           "expected NoSuchInput for :archived_at, got #{inspect(stamp_errors)}"
  end

  test "T30 the generated archived and active read actions partition the records" do
    kept = Ash.create!(@document, %{title: "kept"}, action: :open)
    gone = Ash.create!(@document, %{title: "gone"}, action: :open)
    _ = Ash.update!(gone, %{}, action: :archive)

    assert Enum.map(Ash.read!(@document, action: :archived), & &1.title) == ["gone"]
    assert Enum.map(Ash.read!(@document, action: :active), & &1.title) == ["kept"]
    assert Enum.map(@document.archived_records!(), & &1.title) == ["gone"]
    assert kept.title == "kept"
  end

  test "T31 a required reason is enforced by the generated argument" do
    contract = Ash.create!(@contract, %{reference: "c1"}, action: :sign)

    assert {:error, %Ash.Error.Invalid{errors: errors}} =
             Ash.update(contract, %{}, action: :retire)

    assert Enum.any?(errors, fn error ->
             is_struct(error, Ash.Error.Changes.Required) and error.field == :reason and
               error.type == :argument
           end),
           "expected a required-argument error for :reason, got #{inspect(errors)}"
  end

  test "T32 retiring a contract stamps the timestamp, the reason and runs the hook change" do
    contract = Ash.create!(@contract, %{reference: "c1"}, action: :sign)
    retired = Ash.update!(contract, %{reason: :breach}, action: :retire)

    assert retired.retired_at != nil, "the retire action must stamp :retired_at"
    assert retired.archival_reason == :breach
    assert retired.note == "stamped", "the declared hook change must have run"
  end

  test "T33 an audit event is written for every successful archive when audit is enabled" do
    contract = Ash.create!(@contract, %{reference: "c1"}, action: :sign)
    retired = Ash.update!(contract, %{reason: :breach}, action: :retire)
    loaded = Ash.load!(retired, [:archival_events, :archival_event_count])

    assert length(loaded.archival_events) == 1,
           "expected exactly one audit event, got #{inspect(loaded.archival_events)}"

    event = hd(loaded.archival_events)
    assert event.reason_code == "BRC"
    assert event.subject_type == "Lifecycle.Records.Contract"
    assert event.subject_id == contract.id
    assert event.occurred_at == retired.retired_at
    assert loaded.archival_event_count == 1
  end

  test "T34 no audit events are written when audit is disabled" do
    document = Ash.create!(@document, %{title: "quiet"}, action: :open)
    _ = Ash.update!(document, %{}, action: :archive)
    assert Ash.read!(@event) == [], "Document has audit disabled and must not write audit events"
  end

  test "T35 the generated code interface takes the reason as a positional argument" do
    contract = Ash.create!(@contract, %{reference: "c2"}, action: :sign)
    retired = @contract.retire!(contract, :expiry)
    assert retired.archival_reason == :expiry
    assert retired.retired_at != nil
  end

  # -------------------------------------------------- compile-time verifier

  test "T36 a resource that declares no reason is rejected" do
    assert_dsl_error(
      resource_source("HarborNoReasons", ""),
      "HarborNoReasons",
      "archival -> reason ",
      "at least one reason must be declared"
    )
  end

  test "T37 two reasons sharing a code are rejected" do
    assert_dsl_error(
      resource_source("HarborDupCode", "    reason :a, code: \"X\"\n    reason :b, code: \"X\""),
      "HarborDupCode",
      "archival -> reason ",
      "reason code \"X\" is declared more than once"
    )
  end

  test "T38 a default_reason naming an undeclared reason is rejected" do
    assert_dsl_error(
      resource_source(
        "HarborGhostDefault",
        "    reason :a, code: \"A\"\n    default_reason :ghost"
      ),
      "HarborGhostDefault",
      "archival -> default_reason ",
      "default_reason :ghost is not a declared reason"
    )
  end

  test "T39 a default_reason naming a terminal reason is rejected" do
    assert_dsl_error(
      resource_source(
        "HarborTerminalDefault",
        "    reason :a, code: \"A\", terminal?: true\n    default_reason :a"
      ),
      "HarborTerminalDefault",
      "archival -> default_reason ",
      "default_reason :a is terminal"
    )
  end

  test "T40 enabling audit without an event_resource is rejected" do
    assert_dsl_error(
      resource_source(
        "HarborAuditNoResource",
        "    reason :a, code: \"A\"\n    audit do\n      enabled? true\n    end"
      ),
      "HarborAuditNoResource",
      "archival -> audit -> event_resource ",
      "event_resource is required when audit is enabled"
    )
  end

  test "T41 declaring default_reason twice is rejected by the DSL itself" do
    messages =
      dsl_error_messages(
        resource_source(
          "HarborTwoDefaults",
          "    reason :a, code: \"A\"\n    default_reason :a\n    default_reason :a"
        )
      )

    assert Enum.any?(
             messages,
             &String.contains?(&1, "Expected at most one default_reason in [:archival], got 2")
           ),
           "expected the singleton entity violation to be reported, got:\n#{Enum.join(messages, "\n")}"
  end

  test "T42 a reason without a code fails to compile" do
    result =
      try do
        ExUnit.CaptureIO.capture_io(:stderr, fn ->
          Code.compile_string(resource_source("HarborMissingCode", "    reason :a"))
        end)

        :no_error
      rescue
        error -> {error.__struct__, Exception.message(error)}
      end

    assert {Spark.Error.DslError, message} = result
    assert String.contains?(message, "required :code option not found"),
           "expected a missing required option error, got: #{inspect(result)}"
  end

  test "T43 the hook entity is unavailable without the hooks extension" do
    compile_ok!(resource_source("HarborHookControl", "    reason :a, code: \"A\""))

    assert Ash.Resource.Info.attribute(Elixir.HarborHookControl, :archived_at),
           "the control resource must compile and gain the generated archival attributes"

    result =
      try do
        ExUnit.CaptureIO.capture_io(:stderr, fn ->
          Code.compile_string(
            resource_source(
              "HarborHookWithoutExtension",
              "    reason :a, code: \"A\"\n    hook :h, module: Lifecycle.Records.StampNote"
            )
          )
        end)

        :no_error
      rescue
        error -> {error.__struct__, Exception.message(error)}
      end

    assert match?({CompileError, _}, result),
           "expected using `hook` without Lifecycle.Archival.Hooks to be a CompileError, got #{inspect(result)}"
  end

  test "T44 a differently configured resource compiled at runtime works end to end" do
    source =
      resource_source(
        "HarborRuntimeDoc",
        "    timestamp_attribute :gone_at\n    action_name :retire_it\n    reason_required? true\n    reason :only, code: \"ONE\""
      )

    compile_ok!(source)

    assert Ash.Resource.Info.attribute(Elixir.HarborRuntimeDoc, :gone_at),
           "the runtime-compiled resource is missing its :gone_at attribute"

    refute Ash.Resource.Info.attribute(Elixir.HarborRuntimeDoc, :archived_at),
           "the runtime-compiled resource must use :gone_at, not the default :archived_at"

    action = Ash.Resource.Info.action(Elixir.HarborRuntimeDoc, :retire_it)
    assert action, "the runtime-compiled resource is missing its :retire_it action"
    assert action.type == :update
    assert hd(action.arguments).allow_nil? == false
    assert constraints_one_of(hd(action.arguments)) == [:only]
    assert Ash.Resource.Info.action(Elixir.HarborRuntimeDoc, :archived)
    assert Ash.Resource.Info.action(Elixir.HarborRuntimeDoc, :active)

    assert Spark.Dsl.Extension.get_persisted(Elixir.HarborRuntimeDoc, :archival_reason_codes) ==
             %{only: "ONE"}

    record = Ash.create!(Elixir.HarborRuntimeDoc, %{}, action: :create)
    archived = Ash.update!(record, %{reason: :only}, action: :retire_it)
    assert archived.gone_at != nil
    assert archived.archival_reason == :only
    assert Enum.map(Ash.read!(Elixir.HarborRuntimeDoc, action: :archived), & &1.id) == [record.id]
    assert Ash.read!(Elixir.HarborRuntimeDoc, action: :active) == []
  end

  test "T45 a runtime-compiled resource listing only the hooks extension gets everything" do
    source =
      resource_source(
        "HarborRuntimeHooked",
        "    reason :a, code: \"A\"\n    hook :stamp, module: Lifecycle.Records.StampNote",
        "Lifecycle.Archival.Hooks",
        "    attribute :note, :string, allow_nil?: true, public?: true"
      )

    compile_ok!(source)

    assert Ash.Resource.Info.attribute(Elixir.HarborRuntimeHooked, :archived_at),
           "the hooks-only resource is missing the generated :archived_at attribute"

    changes = change_modules(Ash.Resource.Info.action(Elixir.HarborRuntimeHooked, :archive))

    assert length(changes) == 2,
           "expected the archiving change plus the declared hook, got #{inspect(changes)}"

    assert List.last(changes) == @stamp_note

    record = Ash.create!(Elixir.HarborRuntimeHooked, %{}, action: :create)
    archived = Ash.update!(record, %{reason: :a}, action: :archive)
    assert archived.archived_at != nil
    assert archived.note == "stamped"
  end
end

ExUnit.run()
'''


def _run(args, timeout=1800):
    env = os.environ.copy()
    env["MIX_ENV"] = "dev"
    return subprocess.run(
        args,
        cwd=PROJECT_DIR,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )


@pytest.fixture(scope="session")
def suite():
    with open(SCRIPT_PATH, "w", encoding="utf-8") as handle:
        handle.write(SUITE_EXS.lstrip("\n"))

    compiled = _run(["mix", "compile"])
    run = _run(["mix", "run", SCRIPT_PATH])

    results = {}
    for line in run.stdout.splitlines():
        if not line.startswith(MARKER):
            continue
        parts = line[len(MARKER) :].split("@@")
        if len(parts) < 3:
            continue
        name, status, encoded = parts[0], parts[1], parts[2]
        if not name.startswith("test T"):
            continue
        scenario = name[len("test ") :].split(" ", 1)[0]
        try:
            detail = base64.b64decode(encoded).decode("utf-8", "replace")
        except Exception:  # pragma: no cover - defensive
            detail = encoded
        results[scenario] = (status, name, detail)

    return {
        "results": results,
        "compile_returncode": compiled.returncode,
        "compile_output": (compiled.stdout + compiled.stderr)[-6000:],
        "returncode": run.returncode,
        "stdout_tail": run.stdout[-6000:],
        "stderr_tail": run.stderr[-6000:],
    }


def _scenario(suite, scenario_id):
    entry = suite["results"].get(scenario_id)
    if entry is None:
        pytest.fail(
            f"Scenario {scenario_id} did not run. The verification suite is executed with "
            f"`mix run {SCRIPT_PATH}` from {PROJECT_DIR}.\n"
            f"mix compile exit code: {suite['compile_returncode']}\n"
            f"mix compile output (tail):\n{suite['compile_output']}\n"
            f"mix run exit code: {suite['returncode']}\n"
            f"stdout (tail):\n{suite['stdout_tail']}\n"
            f"stderr (tail):\n{suite['stderr_tail']}"
        )

    status, name, detail = entry
    assert suite["compile_returncode"] == 0, (
        "`mix compile` must succeed in /home/user/lifecycle.\n"
        f"{suite['compile_output']}"
    )
    assert status == "pass", f"{name} failed:\n{detail}"


def test_t01_archival_section_is_patchable_singleton_limited_and_nested(suite):
    _scenario(suite, "T01")


def test_t02_archival_section_schema_options_and_defaults(suite):
    _scenario(suite, "T02")


def test_t03_audit_section_schema_options_and_defaults(suite):
    _scenario(suite, "T03")


def test_t04_reason_entity_target_args_identifier_and_schema(suite):
    _scenario(suite, "T04")


def test_t05_default_reason_entity_target_and_args(suite):
    _scenario(suite, "T05")


def test_t06_extension_declares_the_three_transformers(suite):
    _scenario(suite, "T06")


def test_t07_extension_declares_the_archival_verifier(suite):
    _scenario(suite, "T07")


def test_t08_hooks_extension_patches_hook_entity_and_adds_archival(suite):
    _scenario(suite, "T08")


def test_t09_info_timestamp_attribute_getters(suite):
    _scenario(suite, "T09")


def test_t10_info_action_name_and_reason_required_getters(suite):
    _scenario(suite, "T10")


def test_t11_info_audit_getters(suite):
    _scenario(suite, "T11")


def test_t12_info_options_maps_expose_defaults(suite):
    _scenario(suite, "T12")


def test_t13_info_archival_reasons_in_declaration_order(suite):
    _scenario(suite, "T13")


def test_t14_info_archival_default_reason(suite):
    _scenario(suite, "T14")


def test_t15_info_archival_hooks(suite):
    _scenario(suite, "T15")


def test_t16_generated_timestamp_attribute_shape(suite):
    _scenario(suite, "T16")


def test_t17_generated_archival_reason_attribute_constraints(suite):
    _scenario(suite, "T17")


def test_t18_generated_update_action_shape(suite):
    _scenario(suite, "T18")


def test_t19_generated_update_action_reason_argument(suite):
    _scenario(suite, "T19")


def test_t20_generated_archived_and_active_read_actions(suite):
    _scenario(suite, "T20")


def test_t21_declared_hooks_appended_to_action_changes(suite):
    _scenario(suite, "T21")


def test_t22_audit_relationship_and_aggregate_only_when_enabled(suite):
    _scenario(suite, "T22")


def test_t23_reason_codes_are_persisted(suite):
    _scenario(suite, "T23")


def test_t24_generated_code_interfaces_are_defined(suite):
    _scenario(suite, "T24")


def test_t25_hooks_extension_activates_archival_extension(suite):
    _scenario(suite, "T25")


def test_t26_archiving_without_reason_uses_default_reason(suite):
    _scenario(suite, "T26")


def test_t27_archiving_with_explicit_reason(suite):
    _scenario(suite, "T27")


def test_t28_undeclared_reason_is_rejected(suite):
    _scenario(suite, "T28")


def test_t29_archive_action_accepts_no_attribute_input(suite):
    _scenario(suite, "T29")


def test_t30_archived_and_active_read_actions_partition_records(suite):
    _scenario(suite, "T30")


def test_t31_required_reason_is_enforced(suite):
    _scenario(suite, "T31")


def test_t32_retiring_a_contract_runs_the_hook_change(suite):
    _scenario(suite, "T32")


def test_t33_audit_event_written_on_successful_archive(suite):
    _scenario(suite, "T33")


def test_t34_no_audit_events_when_audit_disabled(suite):
    _scenario(suite, "T34")


def test_t35_code_interface_takes_positional_reason(suite):
    _scenario(suite, "T35")


def test_t36_resource_without_reason_is_rejected(suite):
    _scenario(suite, "T36")


def test_t37_duplicate_reason_code_is_rejected(suite):
    _scenario(suite, "T37")


def test_t38_unknown_default_reason_is_rejected(suite):
    _scenario(suite, "T38")


def test_t39_terminal_default_reason_is_rejected(suite):
    _scenario(suite, "T39")


def test_t40_audit_without_event_resource_is_rejected(suite):
    _scenario(suite, "T40")


def test_t41_duplicate_default_reason_is_rejected_by_the_dsl(suite):
    _scenario(suite, "T41")


def test_t42_reason_without_code_fails_to_compile(suite):
    _scenario(suite, "T42")


def test_t43_hook_entity_requires_the_hooks_extension(suite):
    _scenario(suite, "T43")


def test_t44_runtime_compiled_resource_with_other_configuration(suite):
    _scenario(suite, "T44")


def test_t45_runtime_compiled_hooks_only_resource(suite):
    _scenario(suite, "T45")
