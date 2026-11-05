import { useEffect, useState } from "react";

import { api, type ActivityComment, type User } from "./api";

interface ActivityCommentsProps {
  activityType: "poll" | "survey";
  activityId: number;
  user: User | null;
  canComment: boolean;
  canModerate: boolean;
  onRequireAuth: () => void;
  onError: (message: string) => void;
  onNotice: (message: string) => void;
}

export default function ActivityComments({
  activityType,
  activityId,
  user,
  canComment,
  canModerate,
  onRequireAuth,
  onError,
  onNotice,
}: ActivityCommentsProps) {
  const [comments, setComments] = useState<ActivityComment[]>([]);
  const [body, setBody] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let active = true;
    setLoading(true);
    api
      .comments(activityType, activityId)
      .then((result) => {
        if (active) setComments(result);
      })
      .catch((error: unknown) => {
        if (active) {
          onError(
            error instanceof Error ? error.message : "Could not load comments.",
          );
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [activityId, activityType, onError]);

  async function submitComment(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!user) {
      onRequireAuth();
      return;
    }
    setBusy(true);
    onError("");
    try {
      const comment = await api.createComment(activityType, activityId, body);
      setComments((current) => [...current, comment]);
      setBody("");
      onNotice("Your comment was posted.");
    } catch (error) {
      onError(error instanceof Error ? error.message : "Could not post comment.");
    } finally {
      setBusy(false);
    }
  }

  async function toggleModeration(comment: ActivityComment) {
    setBusy(true);
    onError("");
    try {
      const updated = await api.moderateComment(
        activityType,
        activityId,
        comment.id,
        !comment.is_hidden,
      );
      setComments((current) =>
        current.map((entry) => (entry.id === updated.id ? updated : entry)),
      );
      onNotice(updated.is_hidden ? "Comment hidden." : "Comment restored.");
    } catch (error) {
      onError(
        error instanceof Error ? error.message : "Could not moderate comment.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="activity-comments" aria-label="Activity comments">
      <div className="comments-heading">
        <h4>Discussion</h4>
        <span>Account-linked comments</span>
      </div>
      {loading ? (
        <p className="comments-empty">Loading comments…</p>
      ) : comments.length ? (
        <div className="comment-list">
          {comments.map((comment) => (
            <article
              className={comment.is_hidden ? "comment-item comment-hidden" : "comment-item"}
              key={comment.id}
            >
              <div className="comment-byline">
                <strong>{comment.author_name}</strong>
                <time dateTime={comment.created_at}>
                  {new Date(comment.created_at).toLocaleDateString()}
                </time>
              </div>
              <p>{comment.body}</p>
              {comment.is_hidden && <span className="comment-hidden-label">Hidden from members</span>}
              {canModerate && (
                <button
                  className="results-button"
                  disabled={busy}
                  onClick={() => void toggleModeration(comment)}
                >
                  {comment.is_hidden ? "Restore" : "Hide"}
                </button>
              )}
            </article>
          ))}
        </div>
      ) : (
        <p className="comments-empty">No comments yet.</p>
      )}
      {canComment ? (
        user ? (
          <form className="comment-form" onSubmit={(event) => void submitComment(event)}>
            <label className="visually-hidden" htmlFor={`comment-${activityType}-${activityId}`}>
              Write a comment
            </label>
            <textarea
              id={`comment-${activityType}-${activityId}`}
              value={body}
              onChange={(event) => setBody(event.target.value)}
              placeholder="Add to the discussion…"
              maxLength={2000}
              required
            />
            <button className="results-button" disabled={busy || !body.trim()}>
              {busy ? "Posting…" : "Post comment"}
            </button>
          </form>
        ) : (
          <button className="results-button" onClick={onRequireAuth}>
            Sign in to comment
          </button>
        )
      ) : (
        <p className="comments-empty">Comments are closed for this activity.</p>
      )}
    </section>
  );
}
