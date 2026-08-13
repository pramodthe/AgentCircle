import { Gauge, TriangleAlert } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { communityApi, interviewApi, outcomeApi } from "../api";
import { COMMENT_TOPICS } from "../types";
import type { Calibration, CommunitySettings } from "../types";

interface InterviewSettings {
  interview_enabled: boolean;
  interview_topics: string[];
  disclose_personal: boolean;
}

/** What the agent may say, and to whom. Off until the owner turns it on. */
export default function AgentPermissions() {
  const [community, setCommunity] = useState<CommunitySettings>();
  const [interview, setInterview] = useState<InterviewSettings>();
  const [calibration, setCalibration] = useState<Calibration>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    const [communityRow, interviewRow, calibrationRow] = await Promise.all([
      communityApi.settings(),
      interviewApi.settings(),
      outcomeApi.calibration(),
    ]);
    setCommunity(communityRow);
    setInterview(interviewRow);
    setCalibration(calibrationRow);
  }, []);

  useEffect(() => {
    void load().catch((caught) => setError(caught.message));
  }, [load]);

  const run = async (action: () => Promise<unknown>) => {
    setBusy(true);
    setError("");
    try {
      await action();
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="profile-stack" id="permissions">
      {error && <p className="auth-error" role="alert"><TriangleAlert size={14} /> {error}</p>}

      <section className="profile-surface">
        <header className="profile-surface-heading">
          <span>Agent permissions</span>
          <small>Off until you turn it on</small>
        </header>
        <p className="profile-about-copy">
          Your agent speaks under your name. These switches are the only way it talks
          to other people.
        </p>

        {community && (
          <>
            <label className="toggle-row">
              <input
                type="checkbox"
                checked={community.discoverable}
                disabled={busy}
                onChange={(event) =>
                  run(() => communityApi.updateSettings({
                    ...community, discoverable: event.target.checked,
                  }))}
              />
              <span>
                Let people find me in Discover
                <small> — turn this off to stop appearing in search without leaving</small>
              </span>
            </label>
            <label className="toggle-row">
              <input
                type="checkbox"
                checked={community.photo_search_enabled}
                disabled={busy}
                onChange={(event) =>
                  run(() => communityApi.updateSettings({
                    ...community, photo_search_enabled: event.target.checked,
                  }))}
              />
              <span>
                Let people find me through my photos
                <small> — off unless you turn it on; your photos stay private until then</small>
              </span>
            </label>
            <label className="toggle-row">
              <input
                type="checkbox"
                checked={community.research_enabled}
                disabled={busy}
                onChange={(event) =>
                  run(() => communityApi.updateSettings({
                    ...community, research_enabled: event.target.checked,
                  }))}
              />
              <span>
                Allow deep research about me
                <small> — lets another member's agent gather public professional context
                  on you and cite its sources. Off by default.</small>
              </span>
            </label>
            <label className="toggle-row">
              <input
                type="checkbox"
                checked={community.comment_enabled}
                disabled={busy}
                onChange={(event) =>
                  run(() => communityApi.updateSettings({
                    ...community, comment_enabled: event.target.checked,
                  }))}
              />
              <span>Comment publicly on community posts</span>
            </label>
            <label className="toggle-row">
              <input
                type="checkbox"
                checked={community.review_before_publish}
                disabled={busy || !community.comment_enabled}
                onChange={(event) =>
                  run(() => communityApi.updateSettings({
                    ...community, review_before_publish: event.target.checked,
                  }))}
              />
              <span>Show me each comment before it posts</span>
            </label>
            <div className="topic-grid">
              <span className="consent-label">
                Topics {community.comment_topics.length === 0 && <small>(all)</small>}
              </span>
              {COMMENT_TOPICS.map((topic) => {
                const on = community.comment_topics.includes(topic);
                return (
                  <button
                    key={topic}
                    className={on ? "topic-chip on" : "topic-chip"}
                    disabled={busy || !community.comment_enabled}
                    onClick={() =>
                      run(() => communityApi.updateSettings({
                        ...community,
                        comment_topics: on
                          ? community.comment_topics.filter((t) => t !== topic)
                          : [...community.comment_topics, topic],
                      }))}
                  >
                    {topic.replace(/_/g, " ")}
                  </button>
                );
              })}
            </div>
          </>
        )}

        {interview && (
          <>
            <label className="toggle-row">
              <input
                type="checkbox"
                checked={interview.interview_enabled}
                disabled={busy}
                onChange={(event) =>
                  run(() => interviewApi.updateSettings({
                    ...interview, interview_enabled: event.target.checked,
                  }))}
              />
              <span>Answer other members' interview questions</span>
            </label>
            <label className="toggle-row">
              <input
                type="checkbox"
                checked={interview.disclose_personal}
                disabled={busy || !interview.interview_enabled}
                onChange={(event) =>
                  run(() => interviewApi.updateSettings({
                    ...interview, disclose_personal: event.target.checked,
                  }))}
              />
              <span>Allow personal questions (hobbies, life outside work)</span>
            </label>
            <p className="panel-sub small">
              Contact details are never shared through an agent, whatever these are set to.
            </p>
          </>
        )}
      </section>

      {calibration && calibration.samples > 0 && (
        <section className={calibration.confidence_multiplier < 1 ? "profile-surface damped" : "profile-surface"}>
          <header className="profile-surface-heading">
            <span><Gauge size={14} /> How well it predicts</span>
          </header>
          <p className="profile-about-copy">{calibration.summary}</p>
          <small className="muted">
            {calibration.samples} recorded outcome{calibration.samples === 1 ? "" : "s"} ·
            average miss {Math.round(calibration.mean_error * 100)} pts
            {calibration.confidence_multiplier < 1 &&
              ` · scores damped ×${calibration.confidence_multiplier}`}
          </small>
        </section>
      )}
    </div>
  );
}
