const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "/api/v1";
const TOKEN_KEY = "voxera-token";

export interface User {
  id: number;
  email: string;
  first_name: string;
  last_name: string;
}

export interface PollOption {
  id: number;
  text: string;
  position: number;
  votes?: number;
}

export interface Poll {
  id: number;
  title: string;
  question: string;
  description: string;
  visibility: "public" | "private";
  status: "draft" | "active" | "closed";
  ends_at: string | null;
  created_by: number;
  created_by_name: string;
  organization: number | null;
  organization_name: string | null;
  options: PollOption[];
  response_count: number;
  created_at: string;
}

export interface PollResults {
  poll_id: number;
  question: string;
  total_responses: number;
  options: Array<{
    id: number;
    text: string;
    votes: number;
    percentage: number;
  }>;
}

export interface ActivityComment {
  id: number;
  body: string;
  author: number;
  author_name: string;
  is_hidden: boolean;
  created_at: string;
}

export interface Notification {
  id: number;
  kind: "comment" | "workspace_added";
  message: string;
  actor_name: string;
  organization_slug: string | null;
  poll_id: number | null;
  survey_id: number | null;
  target_title: string;
  created_at: string;
  read_at: string | null;
}

export interface Organization {
  id: number;
  name: string;
  slug: string;
  description: string;
  role: string;
  member_count: number;
  created_at: string;
}

export interface OrganizationMember {
  id: number;
  email: string;
  name: string;
  role: string;
  joined_at: string;
}

export interface OrganizationAnalytics {
  member_count: number;
  poll_count: number;
  active_poll_count: number;
  poll_response_count: number;
  survey_count: number;
  active_survey_count: number;
  survey_response_count: number;
  daily_activity: Array<{
    date: string;
    poll_responses: number;
    survey_responses: number;
  }>;
}

export interface ElectionCandidate {
  id: number;
  user: number;
  name: string;
  statement: string;
  nominated_at: string;
}

export interface Election {
  id: number;
  organization: number;
  organization_name: string;
  title: string;
  description: string;
  status: "draft" | "nominations" | "ready" | "cancelled";
  created_by: number;
  created_at: string;
  nominations_opened_at: string | null;
  nominations_closed_at: string | null;
  eligible_voter_count: number;
  is_eligible: boolean;
  candidates: ElectionCandidate[];
}

export type SurveyQuestionType =
  | "single_choice"
  | "multiple_choice"
  | "short_text"
  | "long_text"
  | "rating";

export interface SurveyOption {
  id: number;
  text: string;
  position: number;
}

export interface SurveyQuestion {
  id: number;
  text: string;
  question_type: SurveyQuestionType;
  is_required: boolean;
  position: number;
  options: SurveyOption[];
}

export interface Survey {
  id: number;
  title: string;
  description: string;
  visibility: "public" | "private";
  status: "draft" | "active" | "closed";
  ends_at: string | null;
  created_by: number;
  created_by_name: string;
  organization: number | null;
  organization_name: string | null;
  questions: SurveyQuestion[];
  response_count: number;
  has_responded: boolean;
  created_at: string;
}

export interface SurveyReport {
  survey_id: number;
  title: string;
  total_responses: number;
  questions: Array<{
    id: number;
    text: string;
    question_type: SurveyQuestionType;
    response_count: number;
    options?: Array<{ id: number; text: string; responses: number }>;
    average_rating?: number | null;
    ratings?: Array<{ rating: number; responses: number }>;
    answers?: Array<{ text: string; submitted_at: string }>;
  }>;
}

interface AuthResponse {
  token: string;
  user: User;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const token = sessionStorage.getItem(TOKEN_KEY);

  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (token) {
    headers.set("Authorization", `Token ${token}`);
  }

  const response = await fetch(`${API_BASE}${path}`, { ...init, headers });
  if (!response.ok) {
    let message = `Request failed (${response.status}).`;
    try {
      const body: unknown = await response.json();
      if (typeof body === "object" && body !== null && "detail" in body) {
        message = String(body.detail);
      } else if (typeof body === "object" && body !== null) {
        message = Object.values(body)
          .flatMap((value) => (Array.isArray(value) ? value : [value]))
          .map(String)
          .join(" ");
      }
    } catch {
      message = `Request failed (${response.status}).`;
    }
    throw new Error(message);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}

async function downloadCsv(path: string, filename: string): Promise<void> {
  const headers = new Headers();
  const token = sessionStorage.getItem(TOKEN_KEY);
  if (token) {
    headers.set("Authorization", `Token ${token}`);
  }

  const response = await fetch(`${API_BASE}${path}`, { headers });
  if (!response.ok) {
    let message = `Request failed (${response.status}).`;
    try {
      const body: unknown = await response.json();
      if (typeof body === "object" && body !== null && "detail" in body) {
        message = String(body.detail);
      }
    } catch {
      message = `Request failed (${response.status}).`;
    }
    throw new Error(message);
  }

  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export const api = {
  async register(payload: {
    email: string;
    password: string;
    first_name: string;
    last_name: string;
  }) {
    const result = await request<AuthResponse>("/auth/register/", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    sessionStorage.setItem(TOKEN_KEY, result.token);
    return result.user;
  },

  async login(email: string, password: string) {
    const result = await request<AuthResponse>("/auth/login/", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    sessionStorage.setItem(TOKEN_KEY, result.token);
    return result.user;
  },

  async currentUser() {
    return request<User>("/auth/me/");
  },

  notifications() {
    return request<Notification[]>("/notifications/");
  },

  unreadNotificationCount() {
    return request<{ unread_count: number }>("/notifications/unread-count/");
  },

  markNotificationRead(notificationId: number) {
    return request<Notification>(`/notifications/${notificationId}/read/`, {
      method: "POST",
    });
  },

  markAllNotificationsRead() {
    return request<{ updated_count: number }>("/notifications/read-all/", {
      method: "POST",
    });
  },

  async logout() {
    try {
      await request<void>("/auth/logout/", { method: "POST" });
    } finally {
      sessionStorage.removeItem(TOKEN_KEY);
    }
  },

  polls() {
    return request<Poll[]>("/polls/");
  },

  createPoll(payload: {
    title: string;
    question: string;
    description: string;
    visibility: "public" | "private";
    ends_at: string | null;
    organization: number | null;
    options: string[];
  }) {
    return request<Poll>("/polls/", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  respond(pollId: number, optionId: number) {
    return request<{ detail: string }>(`/polls/${pollId}/responses/`, {
      method: "POST",
      body: JSON.stringify({ option_id: optionId }),
    });
  },

  results(pollId: number) {
    return request<PollResults>(`/polls/${pollId}/results/`);
  },

  comments(activityType: "poll" | "survey", activityId: number) {
    return request<ActivityComment[]>(
      `/${activityType}s/${activityId}/comments/`,
    );
  },

  createComment(activityType: "poll" | "survey", activityId: number, body: string) {
    return request<ActivityComment>(`/${activityType}s/${activityId}/comments/`, {
      method: "POST",
      body: JSON.stringify({ body }),
    });
  },

  moderateComment(
    activityType: "poll" | "survey",
    activityId: number,
    commentId: number,
    isHidden: boolean,
  ) {
    return request<ActivityComment>(
      `/${activityType}s/${activityId}/comments/${commentId}/moderate/`,
      {
        method: "PATCH",
        body: JSON.stringify({ is_hidden: isHidden }),
      },
    );
  },

  exportPollResults(pollId: number) {
    return downloadCsv(
      `/polls/${pollId}/export-results/`,
      `poll-${pollId}-results.csv`,
    );
  },

  organizations() {
    return request<Organization[]>("/organizations/");
  },

  createOrganization(payload: {
    name: string;
    slug: string;
    description: string;
  }) {
    return request<Organization>("/organizations/", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  members(slug: string) {
    return request<OrganizationMember[]>(`/organizations/${slug}/members/`);
  },

  organizationAnalytics(slug: string) {
    return request<OrganizationAnalytics>(`/organizations/${slug}/analytics/`);
  },

  elections() {
    return request<Election[]>("/elections/");
  },

  createElection(payload: {
    organization: number;
    title: string;
    description: string;
  }) {
    return request<Election>("/elections/", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  openElectionNominations(electionId: number) {
    return request<Election>(`/elections/${electionId}/open-nominations/`, {
      method: "POST",
    });
  },

  closeElectionNominations(electionId: number) {
    return request<Election>(`/elections/${electionId}/close-nominations/`, {
      method: "POST",
    });
  },

  cancelElection(electionId: number) {
    return request<Election>(`/elections/${electionId}/cancel/`, {
      method: "POST",
    });
  },

  nominateForElection(electionId: number, statement: string) {
    return request<ElectionCandidate>(`/elections/${electionId}/nominate/`, {
      method: "POST",
      body: JSON.stringify({ statement }),
    });
  },

  addMember(slug: string, email: string, role: string) {
    return request<OrganizationMember>(`/organizations/${slug}/members/`, {
      method: "POST",
      body: JSON.stringify({ email, role }),
    });
  },

  surveys() {
    return request<Survey[]>("/surveys/");
  },

  createSurvey(payload: {
    title: string;
    description: string;
    visibility: "public" | "private";
    ends_at: string | null;
    organization: number | null;
    questions: Array<{
      text: string;
      question_type: SurveyQuestionType;
      is_required: boolean;
      options: string[];
    }>;
  }) {
    return request<Survey>("/surveys/", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  respondToSurvey(
    surveyId: number,
    answers: Array<Record<string, number | string | number[]>>,
  ) {
    return request<{ detail: string }>(`/surveys/${surveyId}/responses/`, {
      method: "POST",
      body: JSON.stringify({ answers }),
    });
  },

  surveyReport(surveyId: number) {
    return request<SurveyReport>(`/surveys/${surveyId}/report/`);
  },

  exportSurveyReport(surveyId: number) {
    return downloadCsv(
      `/surveys/${surveyId}/export-report/`,
      `survey-${surveyId}-report.csv`,
    );
  },
};
