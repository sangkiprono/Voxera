import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  api,
  type Election,
  type OrganizationAnalytics,
  type OrganizationInvitation,
  type Organization,
  type OrganizationMember,
  type OrganizationSubscriptionStatus,
  type Notification,
  type Poll,
  type PollResults,
  type Survey,
  type User,
} from "./api";
import ActivityComments from "./ActivityComments";
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
  const [organizationApplications, setOrganizationApplications] = useState<Organization[]>([]);
  const [view, setView] = useState<View>("discover");
  const [loading, setLoading] = useState(true);
  const [authRestored, setAuthRestored] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [authOpen, setAuthOpen] = useState(false);
  const [registering, setRegistering] = useState(false);
  const [authChallengeId, setAuthChallengeId] = useState<string | null>(null);
  const [invitationToken, setInvitationToken] = useState<string | null>(() =>
    new URLSearchParams(window.location.search).get("accept_invite"),
  );
  const handledInvitationToken = useRef<string | null>(null);
  const [passwordResetToken, setPasswordResetToken] = useState<string | null>(() =>
    new URLSearchParams(window.location.search).get("reset_password"),
  );
  const [passwordResetRequest, setPasswordResetRequest] = useState(false);
  const [passwordResetSent, setPasswordResetSent] = useState(false);
  const [recoveryCodes, setRecoveryCodes] = useState<string[] | null>(null);
  const [pollFormOpen, setPollFormOpen] = useState(false);
  const [organizationFormOpen, setOrganizationFormOpen] = useState(false);
  const [activeOrganization, setActiveOrganization] = useState<Organization | null>(null);
  const [organizationMembers, setOrganizationMembers] = useState<OrganizationMember[]>([]);
  const [organizationInvitations, setOrganizationInvitations] = useState<OrganizationInvitation[]>([]);
  const [organizationAnalytics, setOrganizationAnalytics] = useState<OrganizationAnalytics | null>(null);
  const [organizationSubscription, setOrganizationSubscription] = useState<OrganizationSubscriptionStatus | null>(null);
  const [organizationElections, setOrganizationElections] = useState<Election[]>([]);
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [unreadNotifications, setUnreadNotifications] = useState(0);
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const [results, setResults] = useState<Record<number, PollResults>>({});
  const [expandedPoll, setExpandedPoll] = useState<number | null>(null);
  const [expandedCommentPoll, setExpandedCommentPoll] = useState<number | null>(null);
  const [choices, setChoices] = useState<Record<number, number>>({});
  const [sharedPollId, setSharedPollId] = useState<number | null>(() => {
    const pollId = Number(new URLSearchParams(window.location.search).get("poll"));
    return Number.isSafeInteger(pollId) && pollId > 0 ? pollId : null;
  });
  const [sharingPoll, setSharingPoll] = useState<Poll | null>(null);

  useEffect(() => {
    const url = new URL(window.location.href);
    if (url.searchParams.has("accept_invite")) {
      url.searchParams.delete("accept_invite");
      window.history.replaceState(null, "", url);
    }
    const verificationToken = url.searchParams.get("verify_email");
    if (verificationToken) {
      url.searchParams.delete("verify_email");
      window.history.replaceState(null, "", url);
      void api.verifyEmail(verificationToken)
        .then(async () => {
          if (sessionStorage.getItem("voxera-token")) {
            setUser(await api.currentUser());
          } else {
            setNotice("Email verified. You can now sign in.");
            setAuthOpen(true);
          }
        })
        .catch((verificationFailure: unknown) => {
          setError(
            verificationFailure instanceof Error
              ? verificationFailure.message
              : "This verification link could not be used.",
          );
        });
    }
    if (url.searchParams.has("reset_password")) {
      setAuthOpen(true);
    }
  }, []);

  const loadData = useCallback(async () => {
    if (!authRestored || (user && (!user.mfa_enrolled || !user.email_verified))) {
      setLoading(false);
      return;
    }
    setError("");
    try {
      const [pollData, surveyData, organizationData, applicationData] = await Promise.all([
        api.polls(),
        api.surveys(),
        user ? api.organizations() : Promise.resolve([]),
        user ? api.organizationApplications() : Promise.resolve([]),
      ]);
      setPolls(pollData);
      setSurveys(surveyData);
      setOrganizations(organizationData);
      setOrganizationApplications(applicationData);
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "We could not load Voxera right now.",
      );
    } finally {
      setLoading(false);
    }
  }, [authRestored, user]);

  useEffect(() => {
    if (invitationToken && authRestored && !user) {
      setRegistering(false);
      setAuthOpen(true);
    }
    if (
      !invitationToken ||
      !authRestored ||
      !user?.email_verified ||
      !user.mfa_enrolled ||
      handledInvitationToken.current === invitationToken
    ) {
      return;
    }
    handledInvitationToken.current = invitationToken;
    void api.acceptOrganizationInvitation(invitationToken)
      .then(async (membership) => {
        setInvitationToken(null);
        setNotice(`You joined ${membership.organization_name}.`);
        await loadData();
      })
      .catch((acceptError: unknown) => {
        setError(
          acceptError instanceof Error
            ? acceptError.message
            : "Could not accept this workspace invitation.",
        );
        setInvitationToken(null);
      });
  }, [authRestored, invitationToken, loadData, user]);

  const loadNotifications = useCallback(async () => {
    if (!user || !user.mfa_enrolled || !user.email_verified) {
      setNotifications([]);
      setUnreadNotifications(0);
      return;
    }
    try {
      const [items, unread] = await Promise.all([
        api.notifications(),
        api.unreadNotificationCount(),
      ]);
      setNotifications(items);
      setUnreadNotifications(unread.unread_count);
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "We could not load your notifications.",
      );
    }
  }, [user]);

  useEffect(() => {
    let active = true;
    async function restoreSession() {
      if (!sessionStorage.getItem("voxera-token")) {
        setLoading(false);
        setAuthRestored(true);
        return;
      }
      try {
        const currentUser = await api.currentUser();
        if (active) setUser(currentUser);
      } catch {
        sessionStorage.removeItem("voxera-token");
      } finally {
        if (active) {
          setLoading(false);
          setAuthRestored(true);
        }
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

  useEffect(() => {
    if (!user) return;
    void loadNotifications();
    const intervalId = window.setInterval(() => void loadNotifications(), 60_000);
    return () => window.clearInterval(intervalId);
  }, [loadNotifications, user]);

  const visiblePolls = useMemo(
    () =>
      sharedPollId !== null
        ? polls.filter((poll) => poll.id === sharedPollId)
        : view === "mine" && user
          ? polls.filter((poll) => poll.created_by === user.id)
          : polls,
    [polls, sharedPollId, user, view],
  );

  function openPollShare(poll: Poll) {
    const url = new URL(window.location.href);
    url.searchParams.set("poll", String(poll.id));
    url.hash = "";
    window.history.replaceState(null, "", url);
    setSharedPollId(poll.id);
    setSharingPoll(poll);
  }

  function clearSharedPoll() {
    const url = new URL(window.location.href);
    url.searchParams.delete("poll");
    window.history.replaceState(null, "", url);
    setSharedPollId(null);
    setView("discover");
  }

  async function copyPollLink() {
    if (!sharingPoll) return;
    const url = new URL(window.location.href);
    url.searchParams.set("poll", String(sharingPoll.id));
    url.hash = "";
    try {
      await navigator.clipboard.writeText(url.toString());
      setNotice("Poll link copied. Send it to anyone you want to invite.");
    } catch (copyError) {
      setError(
        copyError instanceof Error
          ? `Could not copy the poll link: ${copyError.message}`
          : "Could not copy the poll link.",
      );
    }
  }

  async function handleAuth(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    setBusy(true);
    setError("");
    try {
      let nextUser: User | null;
      if (registering) {
        nextUser = await api.register({
            email: String(formData.get("email")),
            password: String(formData.get("password")),
            first_name: String(formData.get("first_name")),
            last_name: String(formData.get("last_name")),
          });
      } else {
        const login = await api.login(
            String(formData.get("email")),
            String(formData.get("password")),
          );
        if (login.challengeId) {
          setAuthChallengeId(login.challengeId);
          return;
        }
        nextUser = login.user ?? null;
      }
      if (!nextUser) throw new Error("Sign-in did not return an account.");
      setUser(nextUser);
      setAuthOpen(false);
      setAuthChallengeId(null);
      setNotice(registering ? "Your Voxera account is ready." : "Welcome back.");
    } catch (authError) {
      setError(authError instanceof Error ? authError.message : "Sign-in failed.");
    } finally {
      setBusy(false);
    }
  }

  async function handleMFALogin(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!authChallengeId) return;
    const formData = new FormData(event.currentTarget);
    setBusy(true);
    setError("");
    try {
      const nextUser = await api.completeMFALogin(
        authChallengeId,
        String(formData.get("mfa_code")).trim(),
      );
      setUser(nextUser);
      setAuthOpen(false);
      setAuthChallengeId(null);
      setNotice("Welcome back.");
    } catch (authError) {
      setError(authError instanceof Error ? authError.message : "Could not verify your code.");
    } finally {
      setBusy(false);
    }
  }

  async function handlePasswordResetRequest(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    setBusy(true);
    setError("");
    try {
      await api.requestPasswordReset(String(formData.get("email")));
      setPasswordResetSent(true);
    } catch (resetError) {
      setError(resetError instanceof Error ? resetError.message : "Could not request a password reset.");
    } finally {
      setBusy(false);
    }
  }

  async function handlePasswordResetConfirm(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!passwordResetToken) return;
    const formData = new FormData(event.currentTarget);
    setBusy(true);
    setError("");
    try {
      await api.confirmPasswordReset(
        passwordResetToken,
        String(formData.get("new_password")),
      );
      const url = new URL(window.location.href);
      url.searchParams.delete("reset_password");
      window.history.replaceState(null, "", url);
      setPasswordResetToken(null);
      setAuthOpen(false);
      setNotice("Password changed. Sign in with your new password.");
    } catch (resetError) {
      setError(resetError instanceof Error ? resetError.message : "Could not reset your password.");
    } finally {
      setBusy(false);
    }
  }

  function handleMFASetupComplete(nextUser: User, codes: string[]) {
    setUser(nextUser);
    setRecoveryCodes(codes);
    setNotice("Authenticator enabled. Save your recovery codes before continuing.");
  }

  async function handleSignOut() {
    setBusy(true);
    try {
      await api.logout();
      setUser(null);
      setOrganizations([]);
      setOrganizationApplications([]);
      setNotifications([]);
      setUnreadNotifications(0);
      setNotificationsOpen(false);
      setView("discover");
      setNotice("You have signed out.");
    } catch (logoutError) {
      setError(
        logoutError instanceof Error ? logoutError.message : "Sign-out failed.",
      );
    } finally {
      setUser(null);
      setOrganizations([]);
      setNotifications([]);
      setUnreadNotifications(0);
      setNotificationsOpen(false);
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
      const poll = await api.createPoll({
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
      openPollShare(poll);
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
      const application = await api.createOrganization({
        name,
        slug,
        description: String(formData.get("description")).trim(),
      });
      setOrganizationFormOpen(false);
      setNotice(
        application.status === "pending"
          ? "Your workspace request was submitted for review."
          : "Your workspace is ready.",
      );
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
      const [members, analytics, subscription, elections, invitations] = await Promise.all([
        api.members(organization.slug),
        canViewAnalytics
          ? api.organizationAnalytics(organization.slug)
          : Promise.resolve(null),
        canViewAnalytics
          ? api.organizationSubscription(organization.slug)
          : Promise.resolve(null),
        api.elections(),
        canViewAnalytics ? api.invitations(organization.slug) : Promise.resolve([]),
      ]);
      setOrganizationMembers(members);
      setOrganizationInvitations(invitations);
      setOrganizationAnalytics(analytics);
      setOrganizationSubscription(subscription);
      setOrganizationElections(
        elections.filter((election) => election.organization === organization.id),
      );
      setActiveOrganization(organization);
    } catch (memberError) {
      setError(
        memberError instanceof Error ? memberError.message : "Could not load members.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function markNotificationRead(notification: Notification) {
    try {
      const updated = await api.markNotificationRead(notification.id);
      setNotifications((current) =>
        current.map((item) => (item.id === updated.id ? updated : item)),
      );
      setUnreadNotifications((count) =>
        notification.read_at === null ? Math.max(0, count - 1) : count,
      );
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Could not mark the notification as read.",
      );
    }
  }

  async function markAllNotificationsRead() {
    try {
      await api.markAllNotificationsRead();
      const readAt = new Date().toISOString();
      setNotifications((current) =>
        current.map((notification) => ({ ...notification, read_at: readAt })),
      );
      setUnreadNotifications(0);
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Could not mark notifications as read.",
      );
    }
  }

  async function openNotification(notification: Notification) {
    await markNotificationRead(notification);
    setNotificationsOpen(false);
    setView(
      notification.organization_slug
        ? "workspaces"
        : notification.survey_id
          ? "surveys"
          : "discover",
    );
  }

  async function refreshOrganizationElections() {
    if (!activeOrganization) return;
    const elections = await api.elections();
    setOrganizationElections(
      elections.filter(
        (election) => election.organization === activeOrganization.id,
      ),
    );
  }

  async function handleCreateElection(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!activeOrganization) return;
    const form = event.currentTarget;
    const formData = new FormData(event.currentTarget);
    setBusy(true);
    setError("");
    try {
      await api.createElection({
        organization: activeOrganization.id,
        title: String(formData.get("election_title")).trim(),
        description: String(formData.get("election_description")).trim(),
      });
      await refreshOrganizationElections();
      setNotice("Election draft created.");
      form.reset();
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Could not create election.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function updateElection(
    election: Election,
    action: "open" | "close" | "cancel" | "nominate",
  ) {
    setBusy(true);
    setError("");
    try {
      if (action === "open") await api.openElectionNominations(election.id);
      else if (action === "close") await api.closeElectionNominations(election.id);
      else if (action === "cancel") await api.cancelElection(election.id);
      else {
        await api.nominateForElection(election.id, "");
      }
      await refreshOrganizationElections();
      setNotice(
        action === "nominate"
          ? "You are nominated."
          : action === "open"
            ? "Nominations are open."
            : action === "close"
              ? "Nominations are closed. Voting is not available."
              : "Election cancelled.",
      );
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Could not update election.",
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
      await api.createInvitation(
        activeOrganization.slug,
        {
          email: String(formData.get("email")),
          role: String(formData.get("role")),
        },
      );
      setOrganizationInvitations(await api.invitations(activeOrganization.slug));
      setNotice("Invitation email sent. It expires in 7 days.");
    } catch (memberError) {
      setError(
        memberError instanceof Error ? memberError.message : "Could not add member.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function revokeInvitation(invitationId: number) {
    if (!activeOrganization) return;
    setBusy(true);
    setError("");
    try {
      await api.revokeInvitation(activeOrganization.slug, invitationId);
      setOrganizationInvitations(await api.invitations(activeOrganization.slug));
      setNotice("Invitation revoked.");
    } catch (revokeError) {
      setError(
        revokeError instanceof Error
          ? revokeError.message
          : "Could not revoke the invitation.",
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
  const maxDailyResponses = organizationAnalytics
    ? Math.max(
        1,
        ...organizationAnalytics.daily_activity.map(
          (day) => day.poll_responses + day.survey_responses,
        ),
      )
    : 1;

  if (user && !user.mfa_enrolled) {
    return (
      <MFASetup
        onComplete={handleMFASetupComplete}
        onSignOut={() => void handleSignOut()}
      />
    );
  }

  if (user && !user.email_verified) {
    return (
      <EmailVerificationGate
        email={user.email}
        onSignOut={() => void handleSignOut()}
      />
    );
  }

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
            <>
              <div className="notification-area">
                <button
                  className="notification-trigger"
                  aria-label={`Notifications${unreadNotifications ? `, ${unreadNotifications} unread` : ""}`}
                  aria-expanded={notificationsOpen}
                  onClick={() => setNotificationsOpen((open) => !open)}
                >
                  <svg aria-hidden="true" viewBox="0 0 24 24" fill="none">
                    <path
                      d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9ZM10 21h4"
                      stroke="currentColor"
                      strokeWidth="1.7"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                  {unreadNotifications > 0 && (
                    <span className="notification-badge">
                      {unreadNotifications > 99 ? "99+" : unreadNotifications}
                    </span>
                  )}
                </button>
                {notificationsOpen && (
                  <section className="notification-panel" aria-label="Notifications">
                    <div className="notification-panel-heading">
                      <strong>Notifications</strong>
                      {unreadNotifications > 0 && (
                        <button
                          className="results-button"
                          onClick={() => void markAllNotificationsRead()}
                        >
                          Mark all read
                        </button>
                      )}
                    </div>
                    {notifications.length ? (
                      <div className="notification-list">
                        {notifications.map((notification) => (
                          <button
                            className={
                              notification.read_at
                                ? "notification-item"
                                : "notification-item notification-unread"
                            }
                            key={notification.id}
                            onClick={() => void openNotification(notification)}
                          >
                            <span>{notification.message}</span>
                            <small>
                              {notification.actor_name} ·{" "}
                              {new Date(notification.created_at).toLocaleDateString()}
                            </small>
                          </button>
                        ))}
                      </div>
                    ) : (
                      <p className="notification-empty">You’re all caught up.</p>
                    )}
                  </section>
                )}
              </div>
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
            </>
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
                {organizationApplications
                  .filter((application) => application.status !== "approved")
                  .map((application) => (
                    <article className="workspace-card" key={application.id}>
                      <span className="workspace-symbol">▦</span>
                      <div className="workspace-card-copy">
                        <h2>{application.name}</h2>
                        <p>{application.description || "Organization workspace request"}</p>
                      </div>
                      <div className="workspace-meta">
                        <span className={`role-pill ${application.status}`}>
                          {application.status === "pending" ? "Pending review" : "Not approved"}
                        </span>
                        {application.review_reason && <span>{application.review_reason}</span>}
                      </div>
                    </article>
                  ))}
                {!loading && organizations.length === 0 && organizationApplications.length === 0 && (
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
                onNotice={(message) => {
                  setNotice(message);
                  void loadNotifications();
                }}
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
                      {sharedPollId !== null
                        ? "You’re viewing a poll someone shared with you."
                        : view === "mine"
                          ? "Your ideas, out in the world."
                          : "A few things people are thinking about."}
                    </span>
                  </div>
                  {sharedPollId !== null ? (
                    <button className="results-button" onClick={clearSharedPoll}>
                      Explore all polls →
                    </button>
                  ) : (
                    <span className="results-count">
                      {visiblePolls.length} {visiblePolls.length === 1 ? "poll" : "polls"}
                    </span>
                  )}
                </section>

                {loading ? (
                  <div className="loading-state"><span className="spinner" /> Finding the conversation…</div>
                ) : visiblePolls.length === 0 ? (
                  <div className="empty-state">
                    <span className="empty-icon">◌</span>
                    <h2>
                      {sharedPollId !== null
                        ? "This poll isn’t available."
                        : view === "mine"
                          ? "Your first question is waiting."
                          : "It’s quiet here for now."}
                    </h2>
                    <p>
                      {sharedPollId !== null
                        ? "It may have been removed, closed to the public, or limited to workspace members."
                        : view === "mine"
                          ? "Start a poll and invite people into the conversation."
                          : "Be the first to ask something worth thinking about."}
                    </p>
                    {sharedPollId !== null ? (
                      <button className="button button-primary" onClick={clearSharedPoll}>Explore all polls</button>
                    ) : (
                      <button className="button button-primary" onClick={openCreatePoll}>Create a poll</button>
                    )}
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

                          {expandedCommentPoll === poll.id && (
                            <ActivityComments
                              activityType="poll"
                              activityId={poll.id}
                              user={user}
                              canComment={!isClosed}
                              canModerate={
                                poll.created_by === user?.id ||
                                ["owner", "admin"].includes(
                                  organizations.find(
                                    (organization) => organization.id === poll.organization,
                                  )?.role ?? "",
                                )
                              }
                              onRequireAuth={() => {
                                setRegistering(false);
                                setAuthOpen(true);
                              }}
                              onError={setError}
                              onNotice={(message) => {
                                setNotice(message);
                                void loadNotifications();
                              }}
                            />
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
                              onClick={() => openPollShare(poll)}
                            >
                              Share poll <span aria-hidden="true">↗</span>
                            </button>
                            <button
                              className="results-button"
                              onClick={() =>
                                setExpandedCommentPoll(
                                  expandedCommentPoll === poll.id ? null : poll.id,
                                )
                              }
                            >
                              {expandedCommentPoll === poll.id
                                ? "Hide discussion"
                                : "Discussion"}
                            </button>
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
        <Modal
          onClose={() => {
            setAuthOpen(false);
            setAuthChallengeId(null);
            setPasswordResetRequest(false);
            setPasswordResetSent(false);
          }}
          title={
            authChallengeId
              ? "Verify it’s you."
              : passwordResetToken
                ? "Choose a new password."
                : passwordResetRequest
                  ? "Reset your password."
                  : registering
                    ? "Find your voice."
                    : "Welcome back."
          }
          eyebrow={
            authChallengeId
              ? "AUTHENTICATOR CHECK"
              : passwordResetToken || passwordResetRequest
                ? "ACCOUNT RECOVERY"
                : "YOUR VOXERA ACCOUNT"
          }
        >
          {passwordResetToken ? (
            <form className="form-stack" onSubmit={(event) => void handlePasswordResetConfirm(event)}>
              <p className="modal-copy">Choose a new password for your account.</p>
              <Field label="New password">
                <input name="new_password" type="password" autoComplete="new-password" minLength={8} required />
              </Field>
              {error && <div className="error-banner" role="alert">{error}</div>}
              <button className="button button-primary form-submit" type="submit" disabled={busy}>
                {busy ? "Updating…" : "Change password"}
              </button>
            </form>
          ) : passwordResetRequest ? (
            passwordResetSent ? (
              <>
                <p className="modal-copy">If an active account matches that email, a reset link will be sent.</p>
                <button className="button button-primary form-submit" onClick={() => {
                  setPasswordResetRequest(false);
                  setPasswordResetSent(false);
                }}>
                  Back to sign in
                </button>
              </>
            ) : (
              <form className="form-stack" onSubmit={(event) => void handlePasswordResetRequest(event)}>
                <p className="modal-copy">Enter your account email. If it matches an active account, we’ll send a one-time reset link.</p>
                <Field label="Email address">
                  <input name="email" type="email" autoComplete="email" required />
                </Field>
                {error && <div className="error-banner" role="alert">{error}</div>}
                <button className="button button-primary form-submit" type="submit" disabled={busy}>
                  {busy ? "Sending…" : "Send reset link"}
                </button>
                <p className="switch-auth"><button type="button" onClick={() => setPasswordResetRequest(false)}>Back to sign in</button></p>
              </form>
            )
          ) : authChallengeId ? (
            <>
              <p className="modal-copy">Enter the current six-digit code from your authenticator app, or a saved recovery code.</p>
              <form className="form-stack" onSubmit={(event) => void handleMFALogin(event)}>
                <Field label="Authenticator or recovery code">
                  <input name="mfa_code" autoComplete="one-time-code" autoFocus required />
                </Field>
                <button className="button button-primary form-submit" type="submit" disabled={busy}>
                  {busy ? "Verifying…" : "Verify and sign in"}
                </button>
              </form>
              <p className="switch-auth">
                <button onClick={() => setAuthChallengeId(null)}>Back to sign in</button>
              </p>
            </>
          ) : (
            <>
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
              {!registering && (
                <p className="switch-auth">
                  <button onClick={() => {
                    setError("");
                    setPasswordResetRequest(true);
                  }}>Forgot your password?</button>
                </p>
              )}
            </>
          )}
        </Modal>
      )}

      {recoveryCodes && (
        <Modal
          onClose={() => setRecoveryCodes(null)}
          title="Save your recovery codes."
          eyebrow="ONE-TIME ACCOUNT RECOVERY"
        >
          <p className="modal-copy">Each code works once if you lose access to your authenticator. Store them somewhere private; Voxera cannot show them again.</p>
          <div className="mfa-recovery-codes">
            {recoveryCodes.map((code) => <code key={code}>{code}</code>)}
          </div>
          <button className="button button-primary form-submit" onClick={() => setRecoveryCodes(null)}>
            I’ve saved these codes
          </button>
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

      {sharingPoll && (
        <Modal
          onClose={() => setSharingPoll(null)}
          title="Share your poll."
          eyebrow="INVITE PEOPLE TO RESPOND"
        >
          <p className="modal-copy">
            Send this link to open the poll directly.
            {sharingPoll.visibility === "private"
              ? " Only members of its workspace can access this private poll."
              : " People need a Voxera account to submit an account-linked response."}
          </p>
          <div className="form-stack">
            <Field label="Poll link">
              <input
                className="share-link-input"
                aria-label="Poll share link"
                readOnly
                value={(() => {
                  const url = new URL(window.location.href);
                  url.searchParams.set("poll", String(sharingPoll.id));
                  url.hash = "";
                  return url.toString();
                })()}
                onFocus={(event) => event.currentTarget.select()}
              />
            </Field>
            <button className="button button-primary form-submit" onClick={() => void copyPollLink()}>
              Copy link
            </button>
          </div>
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
          {organizationSubscription && (
            <section className="workspace-subscription" aria-label="Workspace plan and usage">
              <h3>Plan and usage</h3>
              {organizationSubscription.subscription ? (
                <>
                  <div className="subscription-plan-title">
                    <strong>{organizationSubscription.subscription.plan_name}</strong>
                    <span>
                      {organizationSubscription.subscription.monthly_price_minor === null
                        ? "Price not set"
                        : `${organizationSubscription.subscription.currency} ${(organizationSubscription.subscription.monthly_price_minor / 100).toFixed(2)} / month`}
                    </span>
                  </div>
                  <div><span>Members</span><strong>{organizationSubscription.usage.members} / {organizationSubscription.subscription.max_members ?? "unlimited"}</strong></div>
                  <div><span>Active polls</span><strong>{organizationSubscription.usage.active_polls} / {organizationSubscription.subscription.max_active_polls ?? "unlimited"}</strong></div>
                  <div><span>Active surveys</span><strong>{organizationSubscription.usage.active_surveys} / {organizationSubscription.subscription.max_active_surveys ?? "unlimited"}</strong></div>
                  <small>Status: {organizationSubscription.subscription.status}</small>
                </>
              ) : (
                <p>No subscription plan is assigned to this workspace.</p>
              )}
              <small>Plans are configured by the Voxera administrator. Checkout and payment processing are not enabled.</small>
            </section>
          )}
          {organizationAnalytics && (
            <section className="workspace-analytics" aria-label="Workspace analytics">
              <h3>Workspace activity</h3>
              <div><span>Members</span><strong>{organizationAnalytics.member_count}</strong></div>
              <div><span>Polls</span><strong>{organizationAnalytics.active_poll_count} active / {organizationAnalytics.poll_count} total</strong></div>
              <div><span>Poll responses</span><strong>{organizationAnalytics.poll_response_count}</strong></div>
              <div><span>Surveys</span><strong>{organizationAnalytics.active_survey_count} active / {organizationAnalytics.survey_count} total</strong></div>
              <div><span>Survey responses</span><strong>{organizationAnalytics.survey_response_count}</strong></div>
              <div className="analytics-chart-wrap">
                <span className="analytics-chart-title">Responses · last 30 days</span>
                <div className="analytics-chart" role="img" aria-label="Daily poll and survey response counts for the last 30 days">
                  {organizationAnalytics.daily_activity.map((day) => {
                    const pollHeight = (day.poll_responses / maxDailyResponses) * 100;
                    const surveyHeight = (day.survey_responses / maxDailyResponses) * 100;
                    return (
                      <div className="analytics-day" key={day.date} title={`${day.date}: ${day.poll_responses} poll, ${day.survey_responses} survey responses`}>
                        <span className="analytics-bar-group">
                          <span
                            className={day.poll_responses ? "analytics-bar poll-bar has-activity" : "analytics-bar poll-bar"}
                            style={{ height: `${pollHeight}%` }}
                          />
                          <span
                            className={day.survey_responses ? "analytics-bar survey-bar has-activity" : "analytics-bar survey-bar"}
                            style={{ height: `${surveyHeight}%` }}
                          />
                        </span>
                      </div>
                    );
                  })}
                </div>
                <div className="analytics-legend">
                  <span><i className="poll-legend" /> Polls</span>
                  <span><i className="survey-legend" /> Surveys</span>
                </div>
              </div>
              <div className="analytics-activity-breakdown">
                <h4>Polls with most responses</h4>
                {organizationAnalytics.top_polls.length ? (
                  organizationAnalytics.top_polls.map((poll) => (
                    <div className="analytics-activity-row" key={poll.id}>
                      <span title={poll.title}>{poll.title}</span>
                      <strong>{poll.response_count}</strong>
                    </div>
                  ))
                ) : (
                  <p>No polls have been created yet.</p>
                )}
              </div>
              <div className="analytics-activity-breakdown">
                <h4>Surveys with most responses</h4>
                {organizationAnalytics.top_surveys.length ? (
                  organizationAnalytics.top_surveys.map((survey) => (
                    <div className="analytics-activity-row" key={survey.id}>
                      <span title={survey.title}>{survey.title}</span>
                      <strong>{survey.response_count}</strong>
                    </div>
                  ))
                ) : (
                  <p>No surveys have been created yet.</p>
                )}
              </div>
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
            {["owner", "admin"].includes(activeOrganization.role) && (
              <section className="member-list" aria-label="Workspace invitations">
                <p className="field-label">Invitations</p>
                {organizationInvitations.map((invitation) => (
                  <div className="member-row" key={invitation.id}>
                    <span className="member-name">
                      {invitation.email}
                      <small>
                        {invitation.role} · expires{" "}
                        {new Date(invitation.expires_at).toLocaleDateString()}
                      </small>
                    </span>
                    <span className={`role-pill ${invitation.status}`}>
                      {invitation.status}
                    </span>
                    {invitation.status === "pending" && (
                      <button
                        className="results-button"
                        disabled={busy}
                        onClick={() => void revokeInvitation(invitation.id)}
                      >
                        Revoke
                      </button>
                    )}
                  </div>
                ))}
                {organizationInvitations.length === 0 && <p>No invitations sent.</p>}
              </section>
            )}
          </div>
          <section className="workspace-elections">
            <h3>Organization elections</h3>
            <p className="election-disclaimer">
              Low-stakes setup only. Ballot casting and anonymous voting are not implemented.
            </p>
            {organizationElections.map((election) => {
              const isManager = ["owner", "admin"].includes(activeOrganization.role);
              const alreadyCandidate = election.candidates.some(
                (candidate) => candidate.user === user?.id,
              );
              return (
                <article className="election-item" key={election.id}>
                  <div className="election-item-heading">
                    <strong>{election.title}</strong>
                    <span className={`election-status election-${election.status}`}>
                      {election.status === "nominations"
                        ? "Nominations open"
                        : election.status === "ready"
                          ? "Nominations closed"
                          : election.status}
                    </span>
                  </div>
                  {election.description && <p>{election.description}</p>}
                  {election.status !== "draft" && (
                    <small>{election.eligible_voter_count} eligible members at opening</small>
                  )}
                  {election.candidates.map((candidate) => (
                    <div className="election-candidate" key={candidate.id}>
                      <strong>{candidate.name}</strong>
                      {candidate.statement && <span>{candidate.statement}</span>}
                    </div>
                  ))}
                  <div className="election-actions">
                    {isManager && election.status === "draft" && (
                      <button
                        className="results-button"
                        disabled={busy}
                        onClick={() => void updateElection(election, "open")}
                      >
                        Open nominations
                      </button>
                    )}
                    {election.status === "nominations" &&
                      election.is_eligible &&
                      !alreadyCandidate && (
                        <button
                          className="results-button"
                          disabled={busy}
                          onClick={() => void updateElection(election, "nominate")}
                        >
                          Nominate yourself
                        </button>
                      )}
                    {isManager && election.status === "nominations" && (
                      <button
                        className="results-button"
                        disabled={busy}
                        onClick={() => void updateElection(election, "close")}
                      >
                        Close nominations
                      </button>
                    )}
                    {isManager &&
                      ["draft", "nominations"].includes(election.status) && (
                        <button
                          className="results-button"
                          disabled={busy}
                          onClick={() => void updateElection(election, "cancel")}
                        >
                          Cancel
                        </button>
                      )}
                  </div>
                </article>
              );
            })}
            {["owner", "admin"].includes(activeOrganization.role) && (
              <form className="election-form" onSubmit={(event) => void handleCreateElection(event)}>
                <Field label="Election name">
                  <input name="election_title" maxLength={180} required />
                </Field>
                <Field label="Description (optional)">
                  <textarea name="election_description" rows={2} maxLength={2000} />
                </Field>
                <button className="results-button" disabled={busy}>
                  Create election draft
                </button>
              </form>
            )}
          </section>
          {["owner", "admin"].includes(activeOrganization.role) && (
            <form className="member-form" onSubmit={(event) => void handleAddMember(event)}>
              <p className="field-label">Invite someone by email</p>
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
                  Send invitation <span aria-hidden="true">↗</span>
                </button>
              </div>
              <span className="form-hint">Invitations expire after 7 days and can only be accepted by a verified matching account.</span>
            </form>
          )}
        </Modal>
      )}
    </div>
  );
}

function EmailVerificationGate({
  email,
  onSignOut,
}: {
  email: string;
  onSignOut: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  async function resendVerification() {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const result = await api.resendEmailVerification();
      setNotice(result.detail);
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Could not send a verification link.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="mfa-setup-screen">
      <section className="mfa-setup-panel">
        <p className="eyebrow">VERIFY YOUR EMAIL</p>
        <h1>Check your inbox.</h1>
        <p className="welcome-copy">
          Verify <strong>{email}</strong> using the link we sent before continuing.
        </p>
        {notice && <div className="notice" role="status">{notice}</div>}
        {error && <div className="error-banner" role="alert">{error}</div>}
        <button
          className="button button-primary form-submit"
          onClick={() => void resendVerification()}
          disabled={busy}
        >
          {busy ? "Sending…" : "Resend verification link"}
        </button>
        <button className="results-button" onClick={onSignOut}>Sign out</button>
      </section>
    </main>
  );
}

function MFASetup({
  onComplete,
  onSignOut,
}: {
  onComplete: (user: User, recoveryCodes: string[]) => void;
  onSignOut: () => void;
}) {
  const [setup, setSetup] = useState<{ secret: string } | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [setupAttempt, setSetupAttempt] = useState(0);

  useEffect(() => {
    let active = true;
    void api.startMFASetup()
      .then(({ secret }) => {
        if (active) setSetup({ secret });
      })
      .catch((setupError: unknown) => {
        if (active) {
          setError(
            setupError instanceof Error
              ? setupError.message
              : "Could not start authenticator setup.",
          );
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [setupAttempt]);

  async function confirmSetup(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    setBusy(true);
    setError("");
    try {
      const result = await api.confirmMFASetup(String(formData.get("code")).trim());
      onComplete(result.user, result.recovery_codes);
    } catch (confirmError) {
      setError(
        confirmError instanceof Error
          ? confirmError.message
          : "Could not verify the authenticator code.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="mfa-setup-screen">
      <section className="mfa-setup-panel">
        <p className="eyebrow">SECURE YOUR ACCOUNT</p>
        <h1>Set up your authenticator.</h1>
        <p className="welcome-copy">
          Voxera requires an authenticator code to protect your account. Add this
          key to an authenticator app, then enter the six-digit code it gives you.
        </p>
        {loading ? (
          <div className="loading-state"><span className="spinner" /> Preparing secure setup…</div>
        ) : setup ? (
          <form className="form-stack" onSubmit={(event) => void confirmSetup(event)}>
            <Field label="Authenticator key">
              <code className="mfa-secret">{setup.secret}</code>
            </Field>
            <Field label="Six-digit code">
              <input
                name="code"
                inputMode="numeric"
                autoComplete="one-time-code"
                pattern="[0-9]{6}"
                maxLength={6}
                required
              />
            </Field>
            {error && <div className="error-banner" role="alert">{error}</div>}
            <button className="button button-primary form-submit" type="submit" disabled={busy}>
              {busy ? "Verifying…" : "Enable authenticator"}
            </button>
          </form>
        ) : (
          <>
            {error && <div className="error-banner" role="alert">{error}</div>}
            <button
              className="button button-primary form-submit"
              onClick={() => {
                setError("");
                setLoading(true);
                setSetupAttempt((attempt) => attempt + 1);
              }}
            >
              Retry setup
            </button>
          </>
        )}
        <button className="results-button" onClick={onSignOut}>Sign out</button>
      </section>
    </main>
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
