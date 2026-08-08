# test_archiving.exs

defmodule TestRunner do
  alias Forum.Content.{Post, Comment, Reaction}

  def run do
    run_test("Create Post, Comments and Reactions", fn ->
      # Create a post
      post = Ash.create!(Post, %{title: "First Post"}, authorize?: false)
      if post.title != "First Post", do: raise "post title not first post"
      if not is_nil(post.archived_at), do: raise "post archived_at not nil"
      if not is_nil(post.archive_batch_id), do: raise "post archive_batch_id not nil"

      # Create comments
      comment1 = Ash.create!(Comment, %{body: "Comment 1", post_id: post.id}, authorize?: false)
      comment2 = Ash.create!(Comment, %{body: "Comment 2", post_id: post.id}, authorize?: false)
      if comment1.post_id != post.id, do: raise "comment1 post_id mismatch"

      # Create reactions
      _reaction1 = Ash.create!(Reaction, %{emoji: "👍", comment_id: comment1.id}, authorize?: false)
      _reaction2 = Ash.create!(Reaction, %{emoji: "🎉", comment_id: comment1.id}, authorize?: false)
      _reaction3 = Ash.create!(Reaction, %{emoji: "❤️", comment_id: comment2.id}, authorize?: false)

      # Check comment_count and reaction_count aggregates
      post = Ash.load!(post, :comment_count, authorize?: false)
      if post.comment_count != 2, do: raise "comment_count expected 2, got #{post.comment_count}"

      comment1 = Ash.load!(comment1, :reaction_count, authorize?: false)
      if comment1.reaction_count != 2, do: raise "reaction_count expected 2, got #{comment1.reaction_count}"
    end)

    # 2. Test read scoping
    run_test("Read scoping and load scoping", fn ->
      # Create a post, comment, and reaction
      post = Ash.create!(Post, %{title: "Scoping Post"}, authorize?: false)
      comment = Ash.create!(Comment, %{body: "Scoping Comment", post_id: post.id}, authorize?: false)
      reaction = Ash.create!(Reaction, %{emoji: "🔥", comment_id: comment.id}, authorize?: false)

      # Archive the reaction
      Ash.destroy!(reaction, action: :archive, authorize?: false)

      # Read with ordinary :read (should filter out archived reaction)
      loaded_comment = Ash.load!(comment, [:reactions, :reaction_count], authorize?: false)
      if loaded_comment.reactions != [], do: raise "archived reactions leaked"
      if loaded_comment.reaction_count != 0, do: raise "archived reaction counted"

      # Archive the comment
      Ash.destroy!(comment, action: :archive, authorize?: false)

      # Read post with ordinary :read (should filter out archived comment)
      loaded_post = Ash.load!(post, [:comments, :comment_count], authorize?: false)
      if loaded_post.comments != [], do: raise "archived comments leaked"
      if loaded_post.comment_count != 0, do: raise "archived comment counted"

      # Fetching an archived record through the primary read must produce Ash.Error.Query.NotFound
      result = Ash.get(Comment, comment.id, authorize?: false)
      case result do
        {:error, %Ash.Error.Invalid{errors: [%Ash.Error.Query.NotFound{}]}} -> :ok
        {:error, %Ash.Error.Query.NotFound{}} -> :ok
        other -> raise "Expected NotFound error, got #{inspect(other)}"
      end
    end)

    # 3. Test Archive semantics
    run_test("Archive semantics", fn ->
      post = Ash.create!(Post, %{title: "Archive Post"}, authorize?: false)
      comment1 = Ash.create!(Comment, %{body: "C1", post_id: post.id}, authorize?: false)
      comment2 = Ash.create!(Comment, %{body: "C2", post_id: post.id}, authorize?: false)
      reaction1 = Ash.create!(Reaction, %{emoji: "😀", comment_id: comment1.id}, authorize?: false)
      reaction2 = Ash.create!(Reaction, %{emoji: "😂", comment_id: comment2.id}, authorize?: false)

      # Pre-archive comment1
      comment1_archived = Ash.destroy!(comment1, action: :archive, return_destroyed?: true, authorize?: false)
      if is_nil(comment1_archived.archived_at), do: raise "comment1_archived.archived_at is nil"
      c1_batch_id = comment1_archived.archive_batch_id
      c1_archived_at = comment1_archived.archived_at

      # Wait a tiny bit to make sure timestamps can differ if generated anew
      Process.sleep(10)

      # Now archive the Post
      post_archived = Ash.destroy!(post, action: :archive, return_destroyed?: true, authorize?: false)
      if is_nil(post_archived.archived_at), do: raise "post_archived.archived_at is nil"
      post_batch_id = post_archived.archive_batch_id
      post_archived_at = post_archived.archived_at

      # Two separate archive operations must never produce the same archive_batch_id
      if post_batch_id == c1_batch_id, do: raise "batch ids must differ"

      # Fetch all comments and reactions using :with_archived
      c1_refetched = Ash.get!(Comment, comment1.id, action: :with_archived, authorize?: false)
      c2_refetched = Ash.get!(Comment, comment2.id, action: :with_archived, authorize?: false)
      r1_refetched = Ash.get!(Reaction, reaction1.id, action: :with_archived, authorize?: false)
      r2_refetched = Ash.get!(Reaction, reaction2.id, action: :with_archived, authorize?: false)

      # Descendants that were already archived before the call keep their existing archived_at and archive_batch_id values byte-for-byte.
      if c1_refetched.archive_batch_id != c1_batch_id, do: raise "c1_refetched batch id changed"
      if c1_refetched.archived_at != c1_archived_at, do: raise "c1_refetched archived_at changed"

      # The reaction of the pre-archived comment should also have been archived with the pre-archive batch, not the post's batch
      if r1_refetched.archive_batch_id != c1_batch_id, do: raise "r1_refetched batch id changed"

      # Others (post, comment2, reaction2) are archived together as one generation: same archived_at and same archive_batch_id
      if c2_refetched.archive_batch_id != post_batch_id, do: raise "c2_refetched batch id mismatch"
      if c2_refetched.archived_at != post_archived_at, do: raise "c2_refetched archived_at mismatch"
      if r2_refetched.archive_batch_id != post_batch_id, do: raise "r2_refetched batch id mismatch"
      if r2_refetched.archived_at != post_archived_at, do: raise "r2_refetched archived_at mismatch"

      # If the target record is already archived, the call still succeeds but nothing changes anywhere:
      # target keeps its existing values, and no descendant is modified.
      post_refetched_again = Ash.destroy!(post_archived, action: :archive, return_destroyed?: true, authorize?: false)
      if post_refetched_again.archive_batch_id != post_batch_id, do: raise "post_refetched_again batch changed"
      if post_refetched_again.archived_at != post_archived_at, do: raise "post_refetched_again archived_at changed"
    end)

    # 4. Test Restore semantics
    run_test("Restore semantics", fn ->
      post = Ash.create!(Post, %{title: "Restore Post"}, authorize?: false)
      comment1 = Ash.create!(Comment, %{body: "RC1", post_id: post.id}, authorize?: false)
      comment2 = Ash.create!(Comment, %{body: "RC2", post_id: post.id}, authorize?: false)
      reaction1 = Ash.create!(Reaction, %{emoji: "A", comment_id: comment1.id}, authorize?: false)
      reaction2 = Ash.create!(Reaction, %{emoji: "B", comment_id: comment2.id}, authorize?: false)

      # Archive comment1 first (Batch 1)
      comment1_archived = Ash.destroy!(comment1, action: :archive, return_destroyed?: true, authorize?: false)
      c1_batch_id = comment1_archived.archive_batch_id

      # Archive the entire post (Batch 2) - this archives post, comment2, and reaction2
      post_archived = Ash.destroy!(post, action: :archive, return_destroyed?: true, authorize?: false)
      _post_batch_id = post_archived.archive_batch_id

      # Restore the Post
      post_restored = Ash.update!(post_archived, action: :restore, authorize?: false)
      if not is_nil(post_restored.archived_at), do: raise "post_restored archived_at not nil"
      if not is_nil(post_restored.archive_batch_id), do: raise "post_restored archive_batch_id not nil"

      # Fetch descendants using :with_archived
      c1_refetched = Ash.get!(Comment, comment1.id, action: :with_archived, authorize?: false)
      c2_refetched = Ash.get!(Comment, comment2.id, action: :with_archived, authorize?: false)
      r1_refetched = Ash.get!(Reaction, reaction1.id, action: :with_archived, authorize?: false)
      r2_refetched = Ash.get!(Reaction, reaction2.id, action: :with_archived, authorize?: false)

      # comment2 and reaction2 should be restored (since they had post_batch_id)
      if not is_nil(c2_refetched.archived_at), do: raise "c2_refetched archived_at not nil"
      if not is_nil(c2_refetched.archive_batch_id), do: raise "c2_refetched archive_batch_id not nil"
      if not is_nil(r2_refetched.archived_at), do: raise "r2_refetched archived_at not nil"
      if not is_nil(r2_refetched.archive_batch_id), do: raise "r2_refetched archive_batch_id not nil"

      # comment1 and reaction1 should remain archived with c1_batch_id (different batch id)
      if c1_refetched.archive_batch_id != c1_batch_id, do: raise "c1_refetched batch id changed"
      if r1_refetched.archive_batch_id != c1_batch_id, do: raise "r1_refetched batch id changed"

      # On a record that is not archived the call succeeds and changes nothing, anywhere
      post_restored_again = Ash.update!(post_restored, action: :restore, authorize?: false)
      if not is_nil(post_restored_again.archived_at), do: raise "post_restored_again archived_at not nil"
    end)

    # 5. Test Purge semantics
    run_test("Purge semantics", fn ->
      post = Ash.create!(Post, %{title: "Purge Post"}, authorize?: false)
      comment = Ash.create!(Comment, %{body: "PC", post_id: post.id}, authorize?: false)
      reaction = Ash.create!(Reaction, %{emoji: "P", comment_id: comment.id}, authorize?: false)

      # Try to purge active post (should fail)
      result = Ash.destroy(post, action: :purge, authorize?: false)
      case result do
        {:error, %Ash.Error.Invalid{errors: errors}} ->
          invalid_change_err = Enum.find(errors, fn
            %Ash.Error.Changes.InvalidChanges{fields: [:archived_at], message: "must be archived before it can be purged"} -> true
            _ -> false
          end)
          if is_nil(invalid_change_err), do: raise "Expected specific InvalidChanges error on archived_at"
        other ->
          raise "Expected Invalid error, got #{inspect(other)}"
      end

      # Archive the post
      post_archived = Ash.destroy!(post, action: :archive, return_destroyed?: true, authorize?: false)

      # Purge the archived post
      Ash.destroy!(post_archived, action: :purge, authorize?: false)

      # Verify they are completely gone from storage (even :with_archived should fail to find them)
      case Ash.get(Post, post.id, action: :with_archived, authorize?: false) do
        {:error, %Ash.Error.Invalid{errors: [%Ash.Error.Query.NotFound{}]}} -> :ok
        {:error, %Ash.Error.Query.NotFound{}} -> :ok
        other -> raise "Expected NotFound for Post, got #{inspect(other)}"
      end

      case Ash.get(Comment, comment.id, action: :with_archived, authorize?: false) do
        {:error, %Ash.Error.Invalid{errors: [%Ash.Error.Query.NotFound{}]}} -> :ok
        {:error, %Ash.Error.Query.NotFound{}} -> :ok
        other -> raise "Expected NotFound for Comment, got #{inspect(other)}"
      end

      case Ash.get(Reaction, reaction.id, action: :with_archived, authorize?: false) do
        {:error, %Ash.Error.Invalid{errors: [%Ash.Error.Query.NotFound{}]}} -> :ok
        {:error, %Ash.Error.Query.NotFound{}} -> :ok
        other -> raise "Expected NotFound for Reaction, got #{inspect(other)}"
      end
    end)

    # 6. Test Authorization
    run_test("Authorization policies", fn ->
      post = Ash.create!(Post, %{title: "Auth Post"}, authorize?: false)
      # Archive it
      _post_archived = Ash.destroy!(post, action: :archive, return_destroyed?: true, authorize?: false)

      # Standard read of :archived action with admin actor should succeed
      admin_actor = %{role: :admin}
      results = Post |> Ash.Query.for_read(:archived, %{}, actor: admin_actor) |> Ash.read!(authorize?: true)
      if length(results) == 0, do: raise "Expected to read archived posts as admin"

      # Standard read of :archived action with non-admin actor should fail with Forbidden
      non_admin_actor = %{role: :user}
      result = Post |> Ash.Query.for_read(:archived, %{}, actor: non_admin_actor) |> Ash.read(authorize?: true)
      case result do
        {:error, %Ash.Error.Forbidden{}} -> :ok
        other -> raise "Expected Forbidden error for non-admin on :archived read, got #{inspect(other)}"
      end

      # Standard read of :archived action with nil actor should fail with Forbidden
      result_nil = Post |> Ash.Query.for_read(:archived, %{}, actor: nil) |> Ash.read(authorize?: true)
      case result_nil do
        {:error, %Ash.Error.Forbidden{}} -> :ok
        other -> raise "Expected Forbidden error for nil actor on :archived read, got #{inspect(other)}"
      end

      # Other actions should be permitted for everyone
      # Create a comment as non-admin
      comment = Ash.create!(Comment, %{body: "Auth Comment", post_id: post.id}, actor: non_admin_actor, authorize?: true)
      if comment.body != "Auth Comment", do: raise "Auth Comment body mismatch"

      # Create a comment as nil actor
      comment_nil = Ash.create!(Comment, %{body: "Auth Comment Nil", post_id: post.id}, actor: nil, authorize?: true)
      if comment_nil.body != "Auth Comment Nil", do: raise "Auth Comment Nil body mismatch"
    end)

    # 7. Test Empty Parameter Map Invocation
    run_test("Empty parameter map invocation", fn ->
      # Create a post
      post = Ash.create!(Post, %{title: "Empty Param Post"}, authorize?: false)

      # Check that empty parameter map query works for read actions
      q1 = Ash.Query.for_read(Post, :with_archived, %{})
      if not match?(%Ash.Query{}, q1), do: raise "q1 not a Query"

      q2 = Ash.Query.for_read(Post, :read, %{})
      if not match?(%Ash.Query{}, q2), do: raise "q2 not a Query"

      q3 = Ash.Query.for_read(Post, :archived, %{})
      if not match?(%Ash.Query{}, q3), do: raise "q3 not a Query"

      # Check update/destroy changeset works with empty parameter map
      cs1 = Ash.Changeset.for_destroy(post, :archive, %{})
      if not match?(%Ash.Changeset{}, cs1), do: raise "cs1 not a Changeset"

      cs2 = Ash.Changeset.for_update(post, :restore, %{})
      if not match?(%Ash.Changeset{}, cs2), do: raise "cs2 not a Changeset"

      # Archive it first
      post_archived = Ash.destroy!(post, action: :archive, return_destroyed?: true, authorize?: false)
      cs3 = Ash.Changeset.for_destroy(post_archived, :purge, %{})
      if not match?(%Ash.Changeset{}, cs3), do: raise "cs3 not a Changeset"
    end)

    IO.puts("\nALL TESTS PASSED SUCCESSFULLY!")
  end

  defp run_test(name, func) do
    IO.write("Running: #{name}... ")
    try do
      func.()
      IO.puts("PASSED")
    rescue
      e ->
        IO.puts("FAILED")
        IO.puts(Exception.format(:error, e, __STACKTRACE__))
        System.halt(1)
    end
  end
end

TestRunner.run()
