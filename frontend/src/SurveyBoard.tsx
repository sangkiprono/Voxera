import { useState } from "react";

import {
  api,
  type Organization,
  type Survey,
  type SurveyQuestion,
  type SurveyQuestionType,
  type SurveyReport,
  type User,
} from "./api";
import ActivityComments from "./ActivityComments";

interface SurveyBoardProps {
  surveys: Survey[];
  organizations: Organization[];
  user: User | null;
  mySurveys: boolean;
  busy: boolean;
  onBusyChange: (busy: boolean) => void;
  onRefresh: () => Promise<void>;
  onError: (message: string) => void;
  onNotice: (message: string) => void;
  onRequireAuth: () => void;
  onShowMySurveys: () => void;
  onShowDiscover: () => void;
}

type AnswerValue = number | string | number[];

const questionTypes: Array<{ value: SurveyQuestionType; label: string }> = [
  { value: "single_choice", label: "Single choice" },
  { value: "multiple_choice", label: "Select multiple" },
  { value: "short_text", label: "Short answer" },
  { value: "long_text", label: "Long answer" },
  { value: "rating", label: "Rating, 1–5" },
];

export default function SurveyBoard({
  surveys,
  organizations,
  user,
  mySurveys,
  busy,
  onBusyChange,
  onRefresh,
  onError,
  onNotice,
  onRequireAuth,
  onShowMySurveys,
  onShowDiscover,
}: SurveyBoardProps) {
  const [formOpen, setFormOpen] = useState(false);
  const [questionCount, setQuestionCount] = useState(2);
  const [answers, setAnswers] = useState<Record<number, Record<number, AnswerValue>>>({});
  const [reports, setReports] = useState<Record<number, SurveyReport>>({});
  const [expandedReport, setExpandedReport] = useState<number | null>(null);
  const [expandedComments, setExpandedComments] = useState<number | null>(null);

  const visibleSurveys = mySurveys && user
    ? surveys.filter((survey) => survey.created_by === user.id)
    : surveys;

  async function createSurvey(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    const questions = Array.from({ length: questionCount }, (_, index) => {
      const questionType = String(
        formData.get(`question_type_${index}`),
      ) as SurveyQuestionType;
      const usesOptions =
        questionType === "single_choice" || questionType === "multiple_choice";
      return {
        text: String(formData.get(`question_${index}`)).trim(),
        question_type: questionType,
        is_required: formData.has(`required_${index}`),
        options: usesOptions
          ? formData
              .getAll(`option_${index}`)
              .map((option) => String(option).trim())
              .filter(Boolean)
          : [],
      };
    });

    onBusyChange(true);
    onError("");
    try {
      await api.createSurvey({
        title: String(formData.get("title")).trim(),
        description: String(formData.get("description")).trim(),
        visibility: String(formData.get("visibility")) as "public" | "private",
        ends_at: formData.get("ends_at")
          ? new Date(String(formData.get("ends_at"))).toISOString()
          : null,
        organization: formData.get("organization")
          ? Number(formData.get("organization"))
          : null,
        questions,
      });
      setFormOpen(false);
      setQuestionCount(2);
      onNotice("Your survey is live.");
      await onRefresh();
    } catch (requestError) {
      onError(
        requestError instanceof Error
          ? requestError.message
          : "Could not create survey.",
      );
    } finally {
      onBusyChange(false);
    }
  }

  async function submitResponse(survey: Survey) {
    if (!user) {
      onRequireAuth();
      return;
    }

    const surveyAnswers = answers[survey.id] ?? {};
    const payload: Array<Record<string, number | string | number[]>> = [];
    for (const question of survey.questions) {
      const value = surveyAnswers[question.id];
      if (value === undefined || value === "") continue;
      if (question.question_type === "single_choice" && typeof value === "number") {
        payload.push({ question_id: question.id, option_id: value });
      } else if (question.question_type === "multiple_choice" && Array.isArray(value)) {
        payload.push({ question_id: question.id, option_ids: value });
      } else if (
        (question.question_type === "short_text" ||
          question.question_type === "long_text") &&
        typeof value === "string"
      ) {
        payload.push({ question_id: question.id, text: value });
      } else if (
        question.question_type === "rating" &&
        typeof value === "number"
      ) {
        payload.push({ question_id: question.id, rating: value });
      }
    }

    onBusyChange(true);
    onError("");
    try {
      await api.respondToSurvey(survey.id, payload);
      onNotice("Your survey response has been recorded.");
      await onRefresh();
    } catch (requestError) {
      onError(
        requestError instanceof Error
          ? requestError.message
          : "Could not submit survey response.",
      );
    } finally {
      onBusyChange(false);
    }
  }

  async function toggleReport(surveyId: number) {
    if (expandedReport === surveyId) {
      setExpandedReport(null);
      return;
    }
    onBusyChange(true);
    onError("");
    try {
      const report = await api.surveyReport(surveyId);
      setReports((current) => ({ ...current, [surveyId]: report }));
      setExpandedReport(surveyId);
    } catch (requestError) {
      onError(
        requestError instanceof Error
          ? requestError.message
          : "Could not load survey report.",
      );
    } finally {
      onBusyChange(false);
    }
  }

  async function exportReport(surveyId: number) {
    onBusyChange(true);
    onError("");
    try {
      await api.exportSurveyReport(surveyId);
      onNotice("Survey report downloaded.");
    } catch (requestError) {
      onError(
        requestError instanceof Error
          ? requestError.message
          : "Could not download survey report.",
      );
    } finally {
      onBusyChange(false);
    }
  }

  return (
    <>
      <section className="section-heading">
        <div>
          <h2>{mySurveys ? "Your surveys" : "Surveys to explore"}</h2>
          <span className="section-subtitle">
            {mySurveys
              ? "Your questionnaires and their response reports."
              : "Thoughtful questions, a little more room for an answer."}
          </span>
        </div>
        <div className="survey-heading-actions">
          {user && (
            <button
              className={mySurveys ? "survey-filter active" : "survey-filter"}
              onClick={mySurveys ? onShowDiscover : onShowMySurveys}
            >
              {mySurveys ? "Explore surveys" : "My surveys"}
            </button>
          )}
          <span className="results-count">
            {visibleSurveys.length} {visibleSurveys.length === 1 ? "survey" : "surveys"}
          </span>
          {user && (
            <button
              className="button button-primary survey-create-button"
              onClick={() => setFormOpen(true)}
            >
              ＋ Create a survey
            </button>
          )}
        </div>
      </section>

      {visibleSurveys.length === 0 ? (
        <div className="empty-state">
          <span className="empty-icon">☷</span>
          <h2>{mySurveys ? "Your first survey is waiting." : "No surveys just yet."}</h2>
          <p>
            {mySurveys
              ? "Build a questionnaire and collect thoughtful responses."
              : "Check back soon, or start a survey of your own."}
          </p>
          <button
            className="button button-primary"
            onClick={() => {
              if (!user) onRequireAuth();
              else setFormOpen(true);
            }}
          >
            Create a survey
          </button>
        </div>
      ) : (
        <div className="survey-grid">
          {visibleSurveys.map((survey, index) => {
            const isClosed =
              survey.status !== "active" ||
              (survey.ends_at !== null && new Date(survey.ends_at) <= new Date());
            const report = reports[survey.id];
            const isExpanded = expandedReport === survey.id;
            const organization = organizations.find(
              (entry) => entry.id === survey.organization,
            );
            const canViewReport =
              user?.id === survey.created_by ||
              ["owner", "admin"].includes(organization?.role ?? "");

            return (
              <article
                className="survey-card"
                key={survey.id}
                style={{ animationDelay: `${index * 55}ms` }}
              >
                <div className="poll-card-top">
                  <span
                    className={
                      survey.visibility === "public"
                        ? "visibility-tag"
                        : "visibility-tag private-tag"
                    }
                  >
                    <span className="tag-dot" />
                    {survey.visibility === "public" ? "PUBLIC" : "PRIVATE"}
                  </span>
                  <span className="poll-time">
                    {isClosed ? "Closed" : "Open"}{" "}
                    <span className="time-dot">·</span>{" "}
                    {survey.questions.length}{" "}
                    {survey.questions.length === 1 ? "question" : "questions"}
                  </span>
                </div>
                <h3>{survey.title}</h3>
                {survey.description && (
                  <p className="poll-description">{survey.description}</p>
                )}
                <div className="poll-byline">
                  <span className="mini-avatar">
                    {survey.created_by_name.slice(0, 1).toUpperCase()}
                  </span>
                  <span>{survey.organization_name || survey.created_by_name}</span>
                  <span className="response-total">
                    {survey.response_count}{" "}
                    {survey.response_count === 1 ? "response" : "responses"}
                  </span>
                </div>

                {isExpanded && report ? (
                  <SurveyReportView report={report} />
                ) : (
                  <div className="survey-questions">
                    {survey.questions.map((question) => (
                      <SurveyQuestionField
                        key={question.id}
                        question={question}
                        value={answers[survey.id]?.[question.id]}
                        disabled={survey.has_responded || isClosed}
                        onChange={(value) =>
                          setAnswers((current) => ({
                            ...current,
                            [survey.id]: {
                              ...current[survey.id],
                              [question.id]: value,
                            },
                          }))
                        }
                      />
                    ))}
                    {survey.has_responded && (
                      <p className="survey-complete">
                        ✓ You’ve already submitted a response.
                      </p>
                    )}
                  </div>
                )}

                {expandedComments === survey.id && (
                  <ActivityComments
                    activityType="survey"
                    activityId={survey.id}
                    user={user}
                    canComment={!isClosed}
                    canModerate={canViewReport}
                    onRequireAuth={onRequireAuth}
                    onError={onError}
                    onNotice={onNotice}
                  />
                )}

                <div className="poll-card-footer">
                  {!survey.has_responded && (
                    <button
                      className="button button-primary vote-button"
                      disabled={busy || isClosed}
                      onClick={() => void submitResponse(survey)}
                    >
                      {isClosed ? "Survey closed" : "Submit survey"}{" "}
                      <span aria-hidden="true">↗</span>
                    </button>
                  )}
                  {canViewReport && (
                    <button
                      className="results-button"
                      disabled={busy}
                      onClick={() => void toggleReport(survey.id)}
                    >
                      {isExpanded ? "Back to questions" : "View report"}{" "}
                      <span aria-hidden="true">{isExpanded ? "↗" : "→"}</span>
                    </button>
                  )}
                  {canViewReport && isExpanded && report && (
                    <button
                      className="results-button"
                      disabled={busy}
                      onClick={() => void exportReport(survey.id)}
                    >
                      Download CSV
                    </button>
                  )}
                  <button
                    className="results-button"
                    onClick={() =>
                      setExpandedComments(
                        expandedComments === survey.id ? null : survey.id,
                      )
                    }
                  >
                    {expandedComments === survey.id ? "Hide discussion" : "Discussion"}
                  </button>
                  {!isClosed && !survey.has_responded && (
                    <span className="privacy-note">Account-linked responses</span>
                  )}
                </div>
              </article>
            );
          })}
        </div>
      )}

      {formOpen && (
        <Modal onClose={() => setFormOpen(false)}>
          <p className="eyebrow">SURVEY BUILDER</p>
          <h2 className="survey-modal-title" id="survey-modal-title">
            Make room for a deeper answer.
          </h2>
          <p className="modal-copy">
            Choose from multiple question types. Responses are linked to participant accounts.
          </p>
          <form className="form-stack survey-builder" onSubmit={(event) => void createSurvey(event)}>
            <Field label="Survey title">
              <input
                name="title"
                placeholder="A short name for your survey"
                maxLength={180}
                required
              />
            </Field>
            <Field label="Description (optional)">
              <textarea
                name="description"
                placeholder="Explain what you hope to learn"
                rows={2}
              />
            </Field>
            <div className="form-row">
              <Field label="Who can respond?">
                <select name="visibility" defaultValue="public">
                  <option value="public">Everyone — public</option>
                  <option value="private">My workspace members</option>
                </select>
              </Field>
              <Field label="Close date (optional)">
                <input name="ends_at" type="datetime-local" />
              </Field>
            </div>
            {organizations.length > 0 && (
              <Field label="Post to a workspace">
                <select name="organization" defaultValue="">
                  <option value="">Personal survey</option>
                  {organizations.map((organization) => (
                    <option value={organization.id} key={organization.id}>
                      {organization.name}
                    </option>
                  ))}
                </select>
              </Field>
            )}

            <div className="survey-builder-questions">
              {Array.from({ length: questionCount }, (_, index) => (
                <SurveyQuestionEditor key={index} index={index} />
              ))}
            </div>
            <button
              className="add-question-button"
              type="button"
              disabled={questionCount >= 10}
              onClick={() => setQuestionCount((count) => Math.min(count + 1, 10))}
            >
              ＋ Add a question {questionCount >= 10 ? "(10 maximum)" : ""}
            </button>
            <button
              className="button button-primary form-submit"
              type="submit"
              disabled={busy}
            >
              {busy ? "Publishing…" : "Publish survey"}{" "}
              <span aria-hidden="true">↗</span>
            </button>
          </form>
        </Modal>
      )}
    </>
  );
}

function SurveyQuestionField({
  question,
  value,
  disabled,
  onChange,
}: {
  question: SurveyQuestion;
  value: AnswerValue | undefined;
  disabled: boolean;
  onChange: (value: AnswerValue) => void;
}) {
  return (
    <fieldset className="survey-question-field" disabled={disabled}>
      <legend>
        {question.text}
        {question.is_required && <span className="required-mark"> *</span>}
      </legend>
      {(question.question_type === "single_choice" ||
        question.question_type === "multiple_choice") &&
        question.options.map((option) => {
          const isMultiple = question.question_type === "multiple_choice";
          const selectedOptions = Array.isArray(value) ? value : [];
          const checked = isMultiple
            ? selectedOptions.includes(option.id)
            : value === option.id;
          return (
            <label
              className={checked ? "option-row chosen" : "option-row"}
              key={option.id}
            >
              <input
                type={isMultiple ? "checkbox" : "radio"}
                name={`survey-${question.id}`}
                checked={checked}
                onChange={() => {
                  if (isMultiple) {
                    onChange(
                      checked
                        ? selectedOptions.filter((id) => id !== option.id)
                        : [...selectedOptions, option.id],
                    );
                  } else {
                    onChange(option.id);
                  }
                }}
              />
              <span className="radio-mark" />
              <span>{option.text}</span>
            </label>
          );
        })}
      {(question.question_type === "short_text" ||
        question.question_type === "long_text") &&
        (question.question_type === "long_text" ? (
          <textarea
            className="survey-answer-text"
            maxLength={1000}
            rows={3}
            placeholder="Write your answer…"
            value={typeof value === "string" ? value : ""}
            onChange={(event) => onChange(event.target.value)}
          />
        ) : (
          <input
            className="survey-answer-text"
            maxLength={1000}
            placeholder="Write your answer…"
            value={typeof value === "string" ? value : ""}
            onChange={(event) => onChange(event.target.value)}
          />
        ))}
      {question.question_type === "rating" && (
        <div className="rating-options" role="group" aria-label="Rating from 1 to 5">
          {[1, 2, 3, 4, 5].map((rating) => (
            <label
              className={value === rating ? "rating-choice selected" : "rating-choice"}
              key={rating}
            >
              <input
                type="radio"
                name={`survey-${question.id}`}
                value={rating}
                checked={value === rating}
                onChange={() => onChange(rating)}
              />
              {rating}
            </label>
          ))}
          <span className="rating-caption">Not at all → Very</span>
        </div>
      )}
    </fieldset>
  );
}

function SurveyQuestionEditor({ index }: { index: number }) {
  const [questionType, setQuestionType] =
    useState<SurveyQuestionType>("single_choice");
  const usesOptions =
    questionType === "single_choice" || questionType === "multiple_choice";

  return (
    <section className="question-editor">
      <div className="question-editor-top">
        <span className="question-number">QUESTION {index + 1}</span>
        <label className="required-toggle">
          <input name={`required_${index}`} type="checkbox" defaultChecked />
          Required
        </label>
      </div>
      <Field label="Question">
        <input
          name={`question_${index}`}
          placeholder="What would you like to ask?"
          maxLength={500}
          required
        />
      </Field>
      <Field label="Answer type">
        <select
          name={`question_type_${index}`}
          value={questionType}
          onChange={(event) =>
            setQuestionType(event.target.value as SurveyQuestionType)
          }
        >
          {questionTypes.map((option) => (
            <option value={option.value} key={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </Field>
      {usesOptions && (
        <div className="options-field question-options">
          <span className="field-label">Answer choices (at least two)</span>
          <input
            name={`option_${index}`}
            placeholder="First choice"
            maxLength={160}
            required
          />
          <input
            name={`option_${index}`}
            placeholder="Second choice"
            maxLength={160}
            required
          />
          <input
            name={`option_${index}`}
            placeholder="Third choice (optional)"
            maxLength={160}
          />
          <input
            name={`option_${index}`}
            placeholder="Fourth choice (optional)"
            maxLength={160}
          />
        </div>
      )}
    </section>
  );
}

function SurveyReportView({ report }: { report: SurveyReport }) {
  return (
    <div className="survey-report">
      <p className="survey-report-total">
        {report.total_responses} total{" "}
        {report.total_responses === 1 ? "response" : "responses"}
      </p>
      {report.questions.map((question) => (
        <section className="report-question" key={question.id}>
          <h4>{question.text}</h4>
          <p>{question.response_count} answers</p>
          {question.options?.map((option) => (
            <div className="report-option" key={option.id}>
              <span>{option.text}</span>
              <span>{option.responses}</span>
            </div>
          ))}
          {question.ratings && (
            <div className="report-rating">
              <strong>{question.average_rating ?? "—"}</strong>
              <span>average out of 5</span>
              {question.ratings.map((rating) => (
                <div className="report-option" key={rating.rating}>
                  <span>{rating.rating} out of 5</span>
                  <span>{rating.responses}</span>
                </div>
              ))}
            </div>
          )}
          {question.answers?.map((answer, index) => (
            <blockquote className="text-answer" key={`${answer.submitted_at}-${index}`}>
              {answer.text}
            </blockquote>
          ))}
        </section>
      ))}
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="field">
      <span className="field-label">{label}</span>
      {children}
    </label>
  );
}

function Modal({
  onClose,
  children,
}: {
  onClose: () => void;
  children: React.ReactNode;
}) {
  return (
    <div
      className="modal-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <section
        className="modal survey-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="survey-modal-title"
      >
        <button
          className="modal-close"
          onClick={onClose}
          aria-label="Close dialog"
        >
          ×
        </button>
        {children}
      </section>
    </div>
  );
}
