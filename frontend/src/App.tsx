import { useCallback, useEffect, useMemo, useState } from "react";

import {
  api,
  type OrganizationAnalytics,
  type Organization,
  type OrganizationMember,
  type Poll,
  type PollResults,
  type Survey,
  type User,
} from "./api";
import SurveyBoard from "./SurveyBoard";

type View = "discover" | "mine" | "surveys" | "my-surveys" | "workspaces";

function initials(user: User) {
  return `${user.first_name[0] ?? user.email[0]}${user.last_name[0] ?? ""}`.toUpperCase();
}

function App() {
  const [user, setUser] = useState<User | null>(null);
  const [polls, setPolls] = useState<Poll[]>([]);
  const [surveys, setSurveys] = useState<Survey[]>([]);
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [view, setView] = useState<View>("discover");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [authOpen, setAuthOpen] = useState(false);
  const [registering, setRegistering] = useState(false);
  const [pollFormOpen, setPollFormOpen] = useState(false);
  const [organizationFormOpen, setOrganizationFormOpen] = useState(false);
  const [activeOrganization, setActiveOrganization] = useState<Organization | null>(null);
  const [organizationMembers, setOrganizationMembers] = useState<OrganizationMember[]>([]);
  const [organizationAnalytics, setOrganizationAnalytics] = useState<OrganizationAnalytics | null>(null);
  const [results, setResults] = useState<Record<number, PollResults>>({});
  const [expandedPoll, setExpandedPoll] = useState<number | null>(null);
  const [choices, setChoices] = useState<Record<number, number>>({});

  const loadData = useCallback(async () => {
    setError("");
    try {
      const [pollData, surveyData, organizationData] = await Promise.all([
        api.polls(),
        api.surveys(),
        user ? api.organizations() : Promise.resolve([]),
      ]);
      setPolls(pollData);
      setSurveys(surveyData);
      setOrganizations(organizationData);
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "We could not load Voxera right now.",
      );
    } finally {
      setLoading(false);
    }
  }, [user]);

  useEffect(() => {
    let active = true;
    async function restoreSession() {
      if (!sessionStorage.getItem("voxera-token")) {
        setLoading(false);
        return;
      }
      try {
        const currentUser = await api.currentUser();
        if (active) setUser(currentUser);
      } catch {
        sessionStorage.removeItem("voxera-token");
      } finally {
        if (active) setLoading(false);
      }
    }
    void restoreSession();
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  const visiblePolls = useMemo(
    () =>
      view === "mine" && user
        ? polls.filter((poll) => poll.created_by === user.id)
        : polls,
    [polls, user, view],
  );

  async function handleAuth(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    setBusy(true);
    setError("");
    try {
      const nextUser = registering
        ? await api.register({
            email: String(formData.get("email")),
            password: String(formData.get("password")),
            first_name: String(formData.get("first_name")),
            last_name: String(formData.get("last_name")),
          })
        : await api.login(
            String(formData.get("email")),
            String(formData.get("password")),
          );
      setUser(nextUser);
      setAuthOpen(false);
      setNotice(registering ? "Your Voxera account is ready." : "Welcome back.");
    } catch (authError) {
      setError(authError instanceof Error ? authError.message : "Sign-in failed.");
    } finally {
      setBusy(false);
    }
  }

  async function handleSignOut() {
    setBusy(true);
    try {
      await api.logout();
      setUser(null);
      setOrganizations([]);
      setView("discover");
      setNotice("You have signed out.");
    } catch (logoutError) {
      setError(
        logoutError instanceof Error ? logoutError.message : "Sign-out failed.",
      );
    } finally {
      setUser(null);
      setOrganizations([]);
      setView("discover");
      setBusy(false);
    }
  }

  async function handleCreatePoll(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    const options = formData
      .getAll("option")
      .map((option) => String(option).trim())
      .filter(Boolean);
    setBusy(true);
    setError("");
    try {
      await api.createPoll({
        title: String(formData.get("title")).trim(),
        question: String(formData.get("question")).trim(),
        description: String(formData.get("description")).trim(),
        visibility: String(formData.get("visibility")) as "public" | "private",
        ends_at: formData.get("ends_at")
          ? new Date(String(formData.get("ends_at"))).toISOString()
          : null,
        organization: formData.get("organization")
          ? Number(formData.get("organization"))
          : null,
        options,
      });
      setPollFormOpen(false);
      setView("mine");
      setNotice("Your poll is live.");
      await loadData();
    } catch (pollError) {
      setError(pollError instanceof Error ? pollError.message : "Could not create poll.");
    } finally {
      setBusy(false);
    }
  }

  async function handleCreateOrganization(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    const name = String(formData.get("name")).trim();
    const slug = name
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-|-$/g, "");
    setBusy(true);
    setError("");
    try {
      await api.createOrganization({
        name,
        slug,
        description: String(formData.get("description")).trim(),
      });
      setOrganizationFormOpen(false);
      setNotice("Your workspace is ready.");
      await loadData();
    } catch (organizationError) {
      setError(
        organizationError instanceof Error
          ? organizationError.message
          : "Could not create workspace.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function openOrganization(organization: Organization) {
    setError("");
    setBusy(true);
    try {
      const canViewAnalytics = ["owner", "admin"].includes(organization.role);
      const [members, analytics] = await Promise.all([
        api.members(organization.slug),
        canViewAnalytics
          ? api.organizationAnalytics(organization.slug)
          : Promise.resolve(null),
      ]);
      setOrganizationMembers(members);
      setOrganizationAnalytics(analytics);
      setActiveOrganization(organization);
    } catch (memberError) {
      setError(
        memberError instanceof Error ? memberError.message : "Could not load members.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function handleAddMember(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!activeOrganization) return;
    const formData = new FormData(event.currentTarget);
    setBusy(true);
    setError("");
    try {
      await api.addMember(
        activeOrganization.slug,
        String(formData.get("email")),
        String(formData.get("role")),
      );
      const [members, analytics] = await Promise.all([
        api.members(activeOrganization.slug),
        api.organizationAnalytics(activeOrganization.slug),
      ]);
      setOrganizationMembers(members);
      setOrganizationAnalytics(analytics);
      await loadData();
      setNotice("Workspace member added.");
    } catch (memberError) {
      setError(
        memberError instanceof Error ? memberError.message : "Could not add member.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function handleVote(poll: Poll) {
    if (!user) {
      setRegistering(false);
      setAuthOpen(true);
      return;
    }
    const optionId = choices[poll.id];
    if (!optionId) {
      setError("Choose an option before responding.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await api.respond(poll.id, optionId);
      const pollResults = await api.results(poll.id);
      setResults((current) => ({ ...current, [poll.id]: pollResults }));
      setExpandedPoll(poll.id);
      setNotice("Your response has been recorded.");
      await loadData();
    } catch (voteError) {
      setError(voteError instanceof Error ? voteError.message : "Could not record response.");
    } finally {
      setBusy(false);
    }
  }

  async function toggleResults(pollId: number) {
    if (expandedPoll === pollId) {
      setExpandedPoll(null);
      return;
    }
    setBusy(true);
    setError("");
    try {
      const pollResults = await api.results(pollId);
      setResults((current) => ({ ...current, [pollId]: pollResults }));
      setExpandedPoll(pollId);
    } catch (resultError) {
      setError(
        resultError instanceof Error
          ? resultError.message
          : "Could not load poll results.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function exportPollResults(pollId: number) {
    setBusy(true);
    setError("");
    try {
      await api.exportPollResults(pollId);
      setNotice("Poll results downloaded.");
    } catch (exportError) {
      setError(
        exportError instanceof Error
          ? exportError.message
          : "Could not download poll results.",
      );
    } finally {
      setBusy(false);
    }
  }

  function openCreatePoll() {
    if (!user) {
      setRegistering(true);
      setAuthOpen(true);
      return;
    }
    setError("");
    setPollFormOpen(true);
  }

  const greetingName = user?.first_name || "there";

  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="/" aria-label="Voxera home">
          <span className="brand-mark">v</span>
          <span>voxera</span>
        </a>
        <nav className="top-links" aria-label="Main navigation">
          <button
            className={view === "discover" ? "top-link active" : "top-link"}
            onClick={() => setView("discover")}
          >
            Discover
          </button>
          {user && (
            <button
              className={view === "mine" ? "top-link active" : "top-link"}
              onClick={() => setView("mine")}
            >
              My activity
            </button>
          )}
          <button
            className={view === "surveys" || view === "my-surveys" ? "top-link active" : "top-link"}
            onClick={() => setView("surveys")}
          >
            Surveys
          </button>
        </nav>
        <div className="top-actions">
          <button className="button button-quiet top-create" onClick={openCreatePoll}>
            <span aria-hidden="true">＋</span> Create a poll
          </button>
          {user ? (
            <button
              className="user-chip"
              onClick={() => void handleSignOut()}
              title="Click to sign out"
              disabled={busy}
            >
              <span className="avatar">{initials(user)}</span>
              <span className="user-name">{user.first_name || user.email}</span>
              <span className="sign-out-label">Sign out</span>
            </button>
          ) : (
            <>
              <button
                className="button button-text"
                onClick={() => {
                  setRegistering(false);
                  setAuthOpen(true);
                }}
              >
                Log in
              </button>
              <button
                className="button button-primary top-signup"
                onClick={() => {
                  setRegistering(true);
                  setAuthOpen(true);
                }}
              >
                Get started <span aria-hidden="true">↗</span>
              </button>
            </>
          )}
        </div>
      </header>

      <div className="layout">
        <aside className="sidebar">
          <div className="sidebar-section">
            <p className="sidebar-label">YOUR SPACE</p>
            <button
              className={view === "discover" ? "side-link selected" : "side-link"}
              onClick={() => setView("discover")}
            >
              <span className="side-icon">⌕</span>
              Explore
            </button>
            <button
              className={view === "mine" ? "side-link selected" : "side-link"}
              onClick={() => setView("mine")}
              disabled={!user}
            >
              <span className="side-icon">◷</span>
              My activity
              {user && <span className="side-count">{polls.filter((poll) => poll.created_by === user.id).length}</span>}
            </button>
            <button
              className={view === "workspaces" ? "side-link selected" : "side-link"}
              onClick={() => setView("workspaces")}
              disabled={!user}
            >
              <span className="side-icon">▦</span>
              Workspaces
            </button>
            <button
              className={view === "surveys" || view === "my-surveys" ? "side-link selected" : "side-link"}
              onClick={() => setView("surveys")}
            >
              <span className="side-icon">☷</span>
              Surveys
            </button>
          </div>

          <div className="sidebar-bottom">
            <div className="sidebar-promo">
              <span className="promo-icon">✳</span>
              <p>Good decisions start with listening.</p>
              <span className="promo-caption">Make room for every voice.</span>
            </div>
            <div className="sidebar-footer">
              <span>Made for better decisions</span>
              <span>© Voxera 2026</span>
            </div>
          </div>
        </aside>

        <main className="main-content">
          <div className="content-wrap">
            <div className="welcome-row">
              <div>
                <p className="eyebrow">
                  {view === "workspaces"
                    ? "A PLACE TO WORK TOGETHER"
                    : view === "surveys" || view === "my-surveys"
                      ? "GO BEYOND THE QUICK QUESTION"
                      : "THE FLOOR IS YOURS"}
                </p>
                <h1>
                  {view === "workspaces"
                    ? "Your workspaces"
                    : view === "surveys"
                      ? "Listen a little deeper."
                      : view === "my-surveys"
                        ? "Your surveys"
                    : view === "mine"
                      ? `Your voice, ${greetingName}.`
                      : "What’s on your mind?"}
                </h1>
                <p className="welcome-copy">
                  {view === "workspaces"
                    ? "Bring your team together around the questions that matter."
                    : view === "surveys" || view === "my-surveys"
                      ? "Create a questionnaire or share your perspective with thoughtful answers."
                    : view === "mine"
                      ? "Keep track of the questions you’re asking the world."
                      : "Explore a question. Share your point of view. See what people think."}
                </p>
              </div>
              {view === "surveys" || view === "my-surveys" ? null : view !== "workspaces" ? (
                <button className="button button-primary hero-button" onClick={openCreatePoll}>
                  <span aria-hidden="true">＋</span> Start a poll
                </button>
              ) : (
                <button
                  className="button button-primary hero-button"
                  onClick={() => {
                    if (!user) {
                      setRegistering(true);
                      setAuthOpen(true);
                    } else {
                      setOrganizationFormOpen(true);
                    }
                  }}
                >
                  <span aria-hidden="true">＋</span> New workspace
                </button>
              )}
            </div>

            {notice && (
              <div className="notice" role="status">
                <span>✓</span> {notice}
                <button aria-label="Dismiss notification" onClick={() => setNotice("")}>×</button>
              </div>
            )}
            {error && (
              <div className="error-banner" role="alert">
                <span>{error}</span>
                <button aria-label="Dismiss error" onClick={() => setError("")}>×</button>
              </div>
            )}

            {view === "workspaces" ? (
              <section className="workspace-grid" aria-label="Your workspaces">
                {organizations.map((organization) => (
                  <article className="workspace-card" key={organization.id}>
                    <span className="workspace-symbol">▦</span>
                    <div className="workspace-card-copy">
                      <h2>{organization.name}</h2>
                      <p>{organization.description || "A shared space for your team."}</p>
                    </div>
                    <div className="workspace-meta">
                      <span>{organization.member_count} {organization.member_count === 1 ? "member" : "members"}</span>
                      <span className="role-pill">{organization.role}</span>
                      <button className="manage-members" onClick={() => void openOrganization(organization)} disabled={busy}>
                        Manage members <span aria-hidden="true">→</span>
                      </button>
                    </div>
                  </article>
                ))}
                {!loading && organizations.length === 0 && (
                  <div className="empty-state wide-empty">
                    <span className="empty-icon">▦</span>
                    <h2>Your team’s next big idea starts here.</h2>
                    <p>Create a workspace to bring polls and people together.</p>
                    <button className="button button-primary" onClick={() => {
                      if (user) setOrganizationFormOpen(true);
                      else {
                        setRegistering(true);
                        setAuthOpen(true);
                      }
                    }}>
                      Create a workspace
                    </button>
                  </div>
                )}
              </section>
            ) : view === "surveys" || view === "my-surveys" ? (
              <SurveyBoard
                surveys={surveys}
                organizations={organizations}
                user={user}
                mySurveys={view === "my-surveys"}
                busy={busy}
                onBusyChange={setBusy}
                onRefresh={loadData}
                onError={setError}
                onNotice={setNotice}
                onRequireAuth={() => {
                  setRegistering(false);
                  setAuthOpen(true);
                }}
                onShowMySurveys={() => setView("my-surveys")}
                onShowDiscover={() => setView("surveys")}
              />
            ) : (
              <>
                <section className="section-heading">
                  <div>
                    <h2>{view === "mine" ? "Your polls" : "Open questions"}</h2>
                    <span className="section-subtitle">
                      {view === "mine" ? "Your ideas, out in the world." : "A few things people are thinking about."}
                    </span>
                  </div>
                  <span className="results-count">
                    {visiblePolls.length} {visiblePolls.length === 1 ? "poll" : "polls"}
                  </span>
                </section>

                {loading ? (
                  <div className="loading-state"><span className="spinner" /> Finding the conversation…</div>
                ) : visiblePolls.length === 0 ? (
                  <div className="empty-state">
                    <span className="empty-icon">◌</span>
                    <h2>{view === "mine" ? "Your first question is waiting." : "It’s quiet here for now."}</h2>
                    <p>{view === "mine" ? "Start a poll and invite people into the conversation." : "Be the first to ask something worth thinking about."}</p>
                    <button className="button button-primary" onClick={openCreatePoll}>Create a poll</button>
                  </div>
                ) : (
                  <div className="poll-grid">
                    {visiblePolls.map((poll, index) => {
                      const result = results[poll.id];
                      const isExpanded = expandedPoll === poll.id;
                      const isClosed = poll.status === "closed" || (poll.ends_at && new Date(poll.ends_at) <= new Date());
                      return (
                        <article className="poll-card" key={poll.id} style={{ animationDelay: `${index * 55}ms` }}>
                          <div className="poll-card-top">
                            <span className={poll.visibility === "public" ? "visibility-tag" : "visibility-tag private-tag"}>
                              <span className="tag-dot" />
                              {poll.visibility === "public" ? "PUBLIC" : "PRIVATE"}
                            </span>
                            <span className="poll-time">
                              {isClosed ? "Closed" : "Open"} <span className="time-dot">·</span> {new Date(poll.created_at).toLocaleDateString(undefined, { month: "short", day: "numeric" })}
                            </span>
                          </div>
                          <h3>{poll.question}</h3>
                          {poll.description && <p className="poll-description">{poll.description}</p>}
                          <div className="poll-byline">
                            <span className="mini-avatar">{poll.created_by_name.slice(0, 1).toUpperCase()}</span>
                            <span>{poll.organization_name || poll.created_by_name}</span>
                            {poll.organization_name && <span className="byline-dot">·</span>}
                            <span className="response-total">{poll.response_count} {poll.response_count === 1 ? "response" : "responses"}</span>
                          </div>

                          {isExpanded && result ? (
                            <div className="results-list" aria-label="Poll results">
                              {result.options.map((option) => (
                                <div className="result-row" key={option.id}>
                                  <div className="result-label">
                                    <span>{option.text}</span>
                                    <span>{option.percentage}%</span>
                                  </div>
                                  <div className="result-track">
                                    <span className="result-fill" style={{ width: `${option.percentage}%` }} />
                                  </div>
                                </div>
                              ))}
                              <p className="results-footnote">{result.total_responses} total responses</p>
                              <button
                                className="results-button"
                                disabled={busy}
                                onClick={() => void exportPollResults(poll.id)}
                              >
                                Download CSV
                              </button>
                            </div>
                          ) : (
                            <fieldset className="option-list" disabled={Boolean(isClosed)}>
                              <legend className="visually-hidden">Choose an answer</legend>
                              {poll.options.map((option) => (
                                <label className={choices[poll.id] === option.id ? "option-row chosen" : "option-row"} key={option.id}>
                                  <input
                                    type="radio"
                                    name={`poll-${poll.id}`}
                                    value={option.id}
                                    checked={choices[poll.id] === option.id}
                                    onChange={() => setChoices((current) => ({ ...current, [poll.id]: option.id }))}
                                  />
                                  <span className="radio-mark" />
                                  <span>{option.text}</span>
                                </label>
                              ))}
                            </fieldset>
                          )}

                          <div className="poll-card-footer">
                            {!isExpanded && (
                              <button
                                className="button button-primary vote-button"
                                disabled={busy || Boolean(isClosed)}
                                onClick={() => void handleVote(poll)}
                              >
                                {isClosed ? "Poll closed" : "Submit response"} <span aria-hidden="true">↗</span>
                              </button>
                            )}
                            {!isExpanded && !isClosed && (
                              <span className="privacy-note">Account-linked response</span>
                            )}
                            <button
                              className="results-button"
                              disabled={busy}
                              onClick={() => void toggleResults(poll.id)}
                            >
                              {isExpanded ? "Back to poll" : "View results"} <span aria-hidden="true">{isExpanded ? "↗" : "→"}</span>
                            </button>
                          </div>
                        </article>
                      );
                    })}
                  </div>
                )}
              </>
            )}

            <footer className="page-footer">
              <span>Every voice counts. Every opinion matters.</span>
              <div><a href="#about">About Voxera</a><a href="mailto:hello@voxera.app">Get in touch</a></div>
            </footer>
          </div>
        </main>
      </div>

      {authOpen && (
        <Modal onClose={() => setAuthOpen(false)} title={registering ? "Find your voice." : "Welcome back."} eyebrow="YOUR VOXERA ACCOUNT">
          <p className="modal-copy">{registering ? "Join the conversation and make your opinion count." : "Sign in to pick up where you left off."}</p>
          <form className="form-stack" onSubmit={(event) => void handleAuth(event)}>
            {registering && (
              <div className="form-row">
                <Field label="First name"><input name="first_name" autoComplete="given-name" required /></Field>
                <Field label="Last name"><input name="last_name" autoComplete="family-name" required /></Field>
              </div>
            )}
            <Field label="Email address"><input name="email" type="email" autoComplete="email" placeholder="you@example.com" required /></Field>
            <Field label="Password"><input name="password" type="password" autoComplete={registering ? "new-password" : "current-password"} minLength={8} required /></Field>
            <button className="button button-primary form-submit" type="submit" disabled={busy}>
              {busy ? "One moment…" : registering ? "Create your account" : "Log in"}
            </button>
          </form>
          <p className="switch-auth">
            {registering ? "Already have an account?" : "New to Voxera?"}{" "}
            <button onClick={() => setRegistering(!registering)}>{registering ? "Log in" : "Create an account"}</button>
          </p>
        </Modal>
      )}

      {pollFormOpen && (
        <Modal onClose={() => setPollFormOpen(false)} title="Ask the room." eyebrow="CREATE A POLL">
          <p className="modal-copy">A good question makes space for better answers.</p>
          <form className="form-stack" onSubmit={(event) => void handleCreatePoll(event)}>
            <Field label="Poll title"><input name="title" placeholder="A short name for your poll" maxLength={180} required /></Field>
            <Field label="Your question"><textarea name="question" placeholder="What do you want to know?" maxLength={500} required rows={2} /></Field>
            <Field label="A little context (optional)"><textarea name="description" placeholder="Give people a bit more to go on" rows={2} /></Field>
            <div className="form-row">
              <Field label="Who can see it">
                <select name="visibility" defaultValue="public"><option value="public">Everyone — public</option><option value="private">My workspace members</option></select>
              </Field>
              <Field label="Close date (optional)"><input name="ends_at" type="datetime-local" /></Field>
            </div>
            {organizations.length > 0 && (
              <Field label="Post to a workspace">
                <select name="organization" defaultValue=""><option value="">Personal poll</option>{organizations.map((organization) => <option value={organization.id} key={organization.id}>{organization.name}</option>)}</select>
              </Field>
            )}
            <div className="options-field">
              <span className="field-label">Answer options</span>
              <input name="option" placeholder="First option" maxLength={160} required />
              <input name="option" placeholder="Second option" maxLength={160} required />
              <input name="option" placeholder="Third option (optional)" maxLength={160} />
              <input name="option" placeholder="Fourth option (optional)" maxLength={160} />
            </div>
            <button className="button button-primary form-submit" type="submit" disabled={busy}>
              {busy ? "Publishing…" : "Publish poll"} <span aria-hidden="true">↗</span>
            </button>
          </form>
        </Modal>
      )}

      {organizationFormOpen && (
        <Modal onClose={() => setOrganizationFormOpen(false)} title="Bring your people together." eyebrow="NEW WORKSPACE">
          <p className="modal-copy">A shared home for the questions your team is asking.</p>
          <form className="form-stack" onSubmit={(event) => void handleCreateOrganization(event)}>
            <Field label="Workspace name"><input name="name" placeholder="e.g. Northstar Collective" maxLength={120} required /></Field>
            <Field label="What’s it for? (optional)"><textarea name="description" placeholder="A little about your team" rows={3} /></Field>
            <button className="button button-primary form-submit" type="submit" disabled={busy}>
              {busy ? "Creating…" : "Create workspace"} <span aria-hidden="true">↗</span>
            </button>
          </form>
        </Modal>
      )}

      {activeOrganization && (
        <Modal
          onClose={() => setActiveOrganization(null)}
          title={activeOrganization.name}
          eyebrow="WORKSPACE MEMBERS"
        >
          <p className="modal-copy">
            {activeOrganization.description || "People working together in this workspace."}
          </p>
          {organizationAnalytics && (
            <section className="workspace-analytics" aria-label="Workspace analytics">
              <h3>Workspace activity</h3>
              <div><span>Members</span><strong>{organizationAnalytics.member_count}</strong></div>
              <div><span>Polls</span><strong>{organizationAnalytics.active_poll_count} active / {organizationAnalytics.poll_count} total</strong></div>
              <div><span>Poll responses</span><strong>{organizationAnalytics.poll_response_count}</strong></div>
              <div><span>Surveys</span><strong>{organizationAnalytics.active_survey_count} active / {organizationAnalytics.survey_count} total</strong></div>
              <div><span>Survey responses</span><strong>{organizationAnalytics.survey_response_count}</strong></div>
            </section>
          )}
          <div className="member-list">
            {organizationMembers.map((member) => (
              <div className="member-row" key={member.id}>
                <span className="member-avatar">{member.name.slice(0, 1).toUpperCase()}</span>
                <span className="member-name">{member.name}<small>{member.email}</small></span>
                <span className="role-pill">{member.role}</span>
              </div>
            ))}
          </div>
          {["owner", "admin"].includes(activeOrganization.role) && (
            <form className="member-form" onSubmit={(event) => void handleAddMember(event)}>
              <p className="field-label">Add someone with an existing Voxera account</p>
              <Field label="Email address">
                <input name="email" type="email" placeholder="teammate@example.com" required />
              </Field>
              <div className="form-row member-form-row">
                <Field label="Workspace role">
                  <select name="role" defaultValue="member">
                    <option value="member">Member</option>
                    <option value="creator">Poll creator</option>
                    <option value="admin">Administrator</option>
                  </select>
                </Field>
                <button className="button button-primary member-submit" type="submit" disabled={busy}>
                  Add member <span aria-hidden="true">↗</span>
                </button>
              </div>
              <span className="form-hint">Invitations by email will be available in a later release.</span>
            </form>
          )}
        </Modal>
      )}
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <label className="field"><span className="field-label">{label}</span>{children}</label>;
}

function Modal({
  eyebrow,
  title,
  onClose,
  children,
}: {
  eyebrow: string;
  title: string;
  onClose: () => void;
  children: React.ReactNode;
}) {
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  return (
    <div className="modal-backdrop" onMouseDown={(event) => {
      if (event.target === event.currentTarget) onClose();
    }}>
      <section className="modal" role="dialog" aria-modal="true" aria-labelledby="modal-title">
        <button className="modal-close" onClick={onClose} aria-label="Close dialog">×</button>
        <p className="eyebrow">{eyebrow}</p>
        <h2 id="modal-title">{title}</h2>
        {children}
      </section>
    </div>
  );
}

export default App;
