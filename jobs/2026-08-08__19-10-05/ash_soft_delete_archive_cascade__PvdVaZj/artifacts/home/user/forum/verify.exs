# Verification script for the cascading soft-delete, global read scoping,
# and archive recovery requirements.

import Ash.Expr
require Ash.Query

alias Forum.Content.Post
alias Forum.Content.Comment
alias Forum.Content.Reaction

IO.puts("=== Starting verification ===\n")

# ---------------------------------------------------------------------------
# Helper: assert a condition, print PASS/FAIL
# ---------------------------------------------------------------------------

assert = fn label, condition ->
  if condition do
    IO.puts("  PASS: #{label}")
  else
    IO.puts("  FAIL: #{label}")
  end
end

assert_equal = fn label, expected, actual ->
  if expected == actual do
    IO.puts("  PASS: #{label}")
  else
    IO.puts("  FAIL: #{label} — expected #{inspect(expected)}, got #{inspect(actual)}")
  end
end

assert_match = fn label, pattern, value ->
  if match?(pattern, value) do
    IO.puts("  PASS: #{label}")
  else
    IO.puts("  FAIL: #{label} — got #{inspect(value)}")
  end
end

# ---------------------------------------------------------------------------
# 1. Create a post
# ---------------------------------------------------------------------------
IO.puts("\n--- 1. Create a post ---")

{:ok, post} =
  Post
  |> Ash.Changeset.for_create(:create, %{title: "Test Post"})
  |> Ash.create(authorize?: false)

assert.("post created with title", post.title == "Test Post")
assert.("post archived_at is nil", post.archived_at == nil)
assert.("post archive_batch_id is nil", post.archive_batch_id == nil)
assert.("post has id", is_binary(post.id))

# ---------------------------------------------------------------------------
# 2. Create comments
# ---------------------------------------------------------------------------
IO.puts("\n--- 2. Create comments ---")

{:ok, comment1} =
  Comment
  |> Ash.Changeset.for_create(:create, %{body: "Comment 1", post_id: post.id})
  |> Ash.create(authorize?: false)

{:ok, comment2} =
  Comment
  |> Ash.Changeset.for_create(:create, %{body: "Comment 2", post_id: post.id})
  |> Ash.create(authorize?: false)

assert.("comment1 created", comment1.body == "Comment 1")
assert.("comment2 created", comment2.body == "Comment 2")

# ---------------------------------------------------------------------------
# 3. Create reactions
# ---------------------------------------------------------------------------
IO.puts("\n--- 3. Create reactions ---")

{:ok, reaction1} =
  Reaction
  |> Ash.Changeset.for_create(:create, %{emoji: "👍", comment_id: comment1.id})
  |> Ash.create(authorize?: false)

{:ok, reaction2} =
  Reaction
  |> Ash.Changeset.for_create(:create, %{emoji: "❤️", comment_id: comment1.id})
  |> Ash.create(authorize?: false)

{:ok, reaction3} =
  Reaction
  |> Ash.Changeset.for_create(:create, %{emoji: "🔥", comment_id: comment2.id})
  |> Ash.create(authorize?: false)

assert.("reaction1 created", reaction1.emoji == "👍")
assert.("reaction2 created", reaction2.emoji == "❤️")
assert.("reaction3 created", reaction3.emoji == "🔥")

# ---------------------------------------------------------------------------
# 4. Verify read scoping — :read returns only live records
# ---------------------------------------------------------------------------
IO.puts("\n--- 4. Read scoping ---")

{:ok, read_posts} = Ash.read(Ash.Query.for_read(Post, :read, %{}), authorize?: false)
assert_equal.(":read returns 1 post", 1, length(read_posts))

{:ok, read_comments} = Ash.read(Ash.Query.for_read(Comment, :read, %{}), authorize?: false)
assert_equal.(":read returns 2 comments", 2, length(read_comments))

{:ok, read_reactions} = Ash.read(Ash.Query.for_read(Reaction, :read, %{}), authorize?: false)
assert_equal.(":read returns 3 reactions", 3, length(read_reactions))

# ---------------------------------------------------------------------------
# 5. Verify aggregates
# ---------------------------------------------------------------------------
IO.puts("\n--- 5. Aggregates ---")

{:ok, [post_with_agg]} = Ash.read(Post |> Ash.Query.load(:comment_count), authorize?: false)
assert_equal.("post comment_count is 2", 2, post_with_agg.comment_count)

c1_id = comment1.id
{:ok, [c1_with_agg]} =
  Comment
  |> Ash.Query.filter(expr(id == ^c1_id))
  |> Ash.Query.load(:reaction_count)
  |> Ash.read(authorize?: false)
assert_equal.("comment1 reaction_count is 2", 2, c1_with_agg.reaction_count)

# ---------------------------------------------------------------------------
# 6. Archive a comment (comment1)
# ---------------------------------------------------------------------------
IO.puts("\n--- 6. Archive comment1 ---")

{:ok, archived_comment1} =
  comment1
  |> Ash.Changeset.for_destroy(:archive, %{}, return_destroyed?: true)
  |> Ash.destroy(authorize?: false)

assert.("comment1 archived_at is set", archived_comment1.archived_at != nil)
assert.("comment1 archive_batch_id is set", archived_comment1.archive_batch_id != nil)
batch_id_1 = archived_comment1.archive_batch_id

# Verify comment1's reactions are also archived with same batch_id
r1_id = reaction1.id
r2_id = reaction2.id

{:ok, [r1]} =
  Reaction
  |> Ash.Query.for_read(:with_archived, %{})
  |> Ash.Query.filter(expr(id == ^r1_id))
  |> Ash.read(authorize?: false)

{:ok, [r2]} =
  Reaction
  |> Ash.Query.for_read(:with_archived, %{})
  |> Ash.Query.filter(expr(id == ^r2_id))
  |> Ash.read(authorize?: false)

assert.("reaction1 archived_at is set", r1.archived_at != nil)
assert.("reaction1 has same batch_id as comment1", r1.archive_batch_id == batch_id_1)
assert.("reaction2 archived_at is set", r2.archived_at != nil)
assert.("reaction2 has same batch_id as comment1", r2.archive_batch_id == batch_id_1)

# Verify comment2 is NOT archived (different comment)
c2_id = comment2.id
{:ok, [c2]} =
  Comment
  |> Ash.Query.for_read(:with_archived, %{})
  |> Ash.Query.filter(expr(id == ^c2_id))
  |> Ash.read(authorize?: false)
assert.("comment2 is NOT archived", c2.archived_at == nil)

# Verify reaction3 is NOT archived (belongs to comment2)
r3_id = reaction3.id
{:ok, [r3]} =
  Reaction
  |> Ash.Query.for_read(:with_archived, %{})
  |> Ash.Query.filter(expr(id == ^r3_id))
  |> Ash.read(authorize?: false)
assert.("reaction3 is NOT archived", r3.archived_at == nil)

# ---------------------------------------------------------------------------
# 7. Verify :read scoping hides archived records
# ---------------------------------------------------------------------------
IO.puts("\n--- 7. Read scoping after archive ---")

{:ok, read_comments2} = Ash.read(Ash.Query.for_read(Comment, :read, %{}), authorize?: false)
assert_equal.(":read returns only 1 live comment", 1, length(read_comments2))

{:ok, read_reactions2} = Ash.read(Ash.Query.for_read(Reaction, :read, %{}), authorize?: false)
assert_equal.(":read returns only 1 live reaction", 1, length(read_reactions2))

# Verify :archived returns only archived
{:ok, archived_comments} = Ash.read(Ash.Query.for_read(Comment, :archived, %{}), authorize?: false)
assert_equal.(":archived returns 1 archived comment", 1, length(archived_comments))

# Verify :with_archived returns all
{:ok, all_comments} = Ash.read(Ash.Query.for_read(Comment, :with_archived, %{}), authorize?: false)
assert_equal.(":with_archived returns 2 comments", 2, length(all_comments))

# Verify Ash.get returns NotFound for archived record
get_result = Ash.get(Comment, comment1.id, authorize?: false)
assert_match.("Ash.get archived comment returns NotFound", {:error, %Ash.Error.Query.NotFound{}}, get_result)

# Verify Ash.get returns live record
{:ok, live_comment} = Ash.get(Comment, comment2.id, authorize?: false)
assert.("Ash.get live comment succeeds", live_comment.id == comment2.id)

# ---------------------------------------------------------------------------
# 8. Verify aggregates exclude archived
# ---------------------------------------------------------------------------
IO.puts("\n--- 8. Aggregates exclude archived ---")

{:ok, [post_with_agg2]} = Ash.read(Post |> Ash.Query.load(:comment_count), authorize?: false)
assert_equal.("post comment_count is 1 (archived excluded)", 1, post_with_agg2.comment_count)

# ---------------------------------------------------------------------------
# 9. Archive comment1 again (already archived — should be no-op)
# ---------------------------------------------------------------------------
IO.puts("\n--- 9. Re-archive comment1 (already archived) ---")

{:ok, re_archived} =
  archived_comment1
  |> Ash.Changeset.for_destroy(:archive, %{}, return_destroyed?: true)
  |> Ash.destroy(authorize?: false)

assert.("re-archive keeps same archived_at", re_archived.archived_at == archived_comment1.archived_at)
assert.("re-archive keeps same batch_id", re_archived.archive_batch_id == archived_comment1.archive_batch_id)

# ---------------------------------------------------------------------------
# 10. Restore comment1
# ---------------------------------------------------------------------------
IO.puts("\n--- 10. Restore comment1 ---")

{:ok, restored_comment1} =
  archived_comment1
  |> Ash.Changeset.for_update(:restore, %{})
  |> Ash.update(authorize?: false)

assert.("restored comment1 archived_at is nil", restored_comment1.archived_at == nil)
assert.("restored comment1 archive_batch_id is nil", restored_comment1.archive_batch_id == nil)

# Verify reactions are also restored
{:ok, [r1_restored]} =
  Reaction
  |> Ash.Query.for_read(:with_archived, %{})
  |> Ash.Query.filter(expr(id == ^r1_id))
  |> Ash.read(authorize?: false)

{:ok, [r2_restored]} =
  Reaction
  |> Ash.Query.for_read(:with_archived, %{})
  |> Ash.Query.filter(expr(id == ^r2_id))
  |> Ash.read(authorize?: false)

assert.("reaction1 restored (archived_at nil)", r1_restored.archived_at == nil)
assert.("reaction1 restored (batch_id nil)", r1_restored.archive_batch_id == nil)
assert.("reaction2 restored (archived_at nil)", r2_restored.archived_at == nil)
assert.("reaction2 restored (batch_id nil)", r2_restored.archive_batch_id == nil)

# ---------------------------------------------------------------------------
# 11. Verify restore doesn't affect records with different batch_id
# ---------------------------------------------------------------------------
IO.puts("\n--- 11. Restore precision — different batch_id not affected ---")

# First archive comment2 separately (different batch_id)
{:ok, archived_comment2} =
  comment2
  |> Ash.Changeset.for_destroy(:archive, %{}, return_destroyed?: true)
  |> Ash.destroy(authorize?: false)

batch_id_2 = archived_comment2.archive_batch_id
assert.("batch_id_1 != batch_id_2", batch_id_1 != batch_id_2)

# reaction3 should be archived with batch_id_2
{:ok, [r3_archived]} =
  Reaction
  |> Ash.Query.for_read(:with_archived, %{})
  |> Ash.Query.filter(expr(id == ^r3_id))
  |> Ash.read(authorize?: false)
assert.("reaction3 archived with batch_id_2", r3_archived.archive_batch_id == batch_id_2)

# Now archive comment1 again (new batch_id)
{:ok, archived_c1_again} =
  restored_comment1
  |> Ash.Changeset.for_destroy(:archive, %{}, return_destroyed?: true)
  |> Ash.destroy(authorize?: false)

batch_id_3 = archived_c1_again.archive_batch_id
assert.("new batch_id_3 differs from batch_id_1", batch_id_3 != batch_id_1)
assert.("new batch_id_3 differs from batch_id_2", batch_id_3 != batch_id_2)

# reactions of comment1 should have batch_id_3 now
{:ok, [r1_again]} =
  Reaction
  |> Ash.Query.for_read(:with_archived, %{})
  |> Ash.Query.filter(expr(id == ^r1_id))
  |> Ash.read(authorize?: false)
assert.("reaction1 has new batch_id_3", r1_again.archive_batch_id == batch_id_3)

# Restore comment1 — should only restore records with batch_id_3, not batch_id_2
{:ok, _restored_c1_again} =
  archived_c1_again
  |> Ash.Changeset.for_update(:restore, %{})
  |> Ash.update(authorize?: false)

# comment2 should still be archived (different batch)
{:ok, [c2_still]} =
  Comment
  |> Ash.Query.for_read(:with_archived, %{})
  |> Ash.Query.filter(expr(id == ^c2_id))
  |> Ash.read(authorize?: false)
assert.("comment2 still archived after restore of comment1", c2_still.archived_at != nil)

# reaction3 should still be archived
{:ok, [r3_still]} =
  Reaction
  |> Ash.Query.for_read(:with_archived, %{})
  |> Ash.Query.filter(expr(id == ^r3_id))
  |> Ash.read(authorize?: false)
assert.("reaction3 still archived after restore of comment1", r3_still.archived_at != nil)

# ---------------------------------------------------------------------------
# 12. Purge validation — cannot purge live record
# ---------------------------------------------------------------------------
IO.puts("\n--- 12. Purge validation ---")

{:ok, live_post} =
  Post
  |> Ash.Changeset.for_create(:create, %{title: "To Purge"})
  |> Ash.create(authorize?: false)

purge_result =
  live_post
  |> Ash.Changeset.for_destroy(:purge, %{})
  |> Ash.destroy(authorize?: false)

assert.("purge live record fails", match?({:error, _}, purge_result))

{:error, purge_error} = purge_result
assert_match.("purge error is Ash.Error.Invalid", %Ash.Error.Invalid{}, purge_error)

has_invalid_changes = Enum.any?(purge_error.errors, fn
  %Ash.Error.Changes.InvalidChanges{fields: [:archived_at], message: "must be archived before it can be purged"} -> true
  _ -> false
end)
assert.("purge error contains InvalidChanges with correct fields/message", has_invalid_changes)

# ---------------------------------------------------------------------------
# 13. Purge an archived record
# ---------------------------------------------------------------------------
IO.puts("\n--- 13. Purge archived record ---")

# Archive the live_post first
{:ok, archived_post} =
  live_post
  |> Ash.Changeset.for_destroy(:archive, %{}, return_destroyed?: true)
  |> Ash.destroy(authorize?: false)

assert.("post archived for purge test", archived_post.archived_at != nil)

# Now purge it
{:ok, _purged} =
  archived_post
  |> Ash.Changeset.for_destroy(:purge, %{})
  |> Ash.destroy(authorize?: false)

# Verify it's gone
lp_id = live_post.id
{:ok, []} =
  Post
  |> Ash.Query.for_read(:with_archived, %{})
  |> Ash.Query.filter(expr(id == ^lp_id))
  |> Ash.read(authorize?: false)
IO.puts("  PASS: purged post no longer exists")

# ---------------------------------------------------------------------------
# 14. Authorization tests
# ---------------------------------------------------------------------------
IO.puts("\n--- 14. Authorization ---")

admin = %{role: :admin}
non_admin = %{role: :user}

# :archived should be forbidden for non-admin
archived_result =
  Comment
  |> Ash.Query.for_read(:archived, %{})
  |> Ash.read(actor: non_admin, authorize?: true)

assert_match.(":archived forbidden for non-admin", {:error, %Ash.Error.Forbidden{}}, archived_result)

# :archived should work for admin
{:ok, _} =
  Comment
  |> Ash.Query.for_read(:archived, %{})
  |> Ash.read(actor: admin, authorize?: true)

IO.puts("  PASS: :archived allowed for admin")

# :read should work for nil actor
{:ok, _} =
  Comment
  |> Ash.Query.for_read(:read, %{})
  |> Ash.read(actor: nil, authorize?: true)

IO.puts("  PASS: :read allowed for nil actor")

# :read should work for non-admin
{:ok, _} =
  Comment
  |> Ash.Query.for_read(:read, %{})
  |> Ash.read(actor: non_admin, authorize?: true)

IO.puts("  PASS: :read allowed for non-admin")

# :create should work for nil actor
{:ok, _} =
  Comment
  |> Ash.Changeset.for_create(:create, %{body: "auth test", post_id: post.id})
  |> Ash.create(actor: nil, authorize?: true)

IO.puts("  PASS: :create allowed for nil actor")

# ---------------------------------------------------------------------------
# 15. Relationship loading scoping
# ---------------------------------------------------------------------------
IO.puts("\n--- 15. Relationship loading scoping ---")

# Load comments for post — should only include live comments
{:ok, [post_loaded]} = Ash.load(post, :comments, authorize?: false)
assert_equal.("loaded comments count is 1 (only live)", 1, length(post_loaded.comments))

# ---------------------------------------------------------------------------
IO.puts("\n=== Verification complete ===")
