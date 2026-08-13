import {
  ArrowLeft,
  ArrowRight,
  Check,
  FileText,
  Link2,
  Loader2,
  Sparkles,
  Trash2,
  TriangleAlert,
  Upload,
  X,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from "react";
import { useNavigate } from "react-router-dom";
import { personaApi, profileApi } from "../api";
import { useAuth } from "../auth";
import type { Persona, PersonaSource } from "../types";

type StepId = "profile" | "sources" | "extras" | "persona";

const STEPS: Array<{ id: StepId; label: string; blurb: string }> = [
  { id: "profile", label: "Basics", blurb: "Who you are" },
  { id: "sources", label: "Context", blurb: "What your agent learns from" },
  { id: "extras", label: "Personality", blurb: "What you like" },
  { id: "persona", label: "Your agent", blurb: "What it understood" },
];

function ChipInput({
  label,
  hint,
  values,
  onChange,
  placeholder,
}: {
  label: string;
  hint?: string;
  values: string[];
  onChange: (next: string[]) => void;
  placeholder: string;
}) {
  const [draft, setDraft] = useState("");

  const commit = () => {
    const value = draft.trim();
    if (!value) return;
    if (!values.some((item) => item.toLowerCase() === value.toLowerCase())) {
      onChange([...values, value.slice(0, 80)]);
    }
    setDraft("");
  };

  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter" || event.key === ",") {
      event.preventDefault();
      commit();
    } else if (event.key === "Backspace" && !draft && values.length) {
      onChange(values.slice(0, -1));
    }
  };

  return (
    <div className="chip-field">
      <span className="chip-label">{label}</span>
      {hint && <span className="chip-hint">{hint}</span>}
      <div className="chip-box">
        {values.map((value) => (
          <span className="chip" key={value}>
            {value}
            <button
              type="button"
              onClick={() => onChange(values.filter((item) => item !== value))}
              aria-label={`Remove ${value}`}
            >
              <X size={12} />
            </button>
          </span>
        ))}
        <input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={onKeyDown}
          onBlur={commit}
          placeholder={values.length ? "" : placeholder}
        />
      </div>
    </div>
  );
}

export default function Onboarding() {
  const { user, profile, refresh } = useAuth();
  const navigate = useNavigate();
  const fileInput = useRef<HTMLInputElement>(null);

  const [step, setStep] = useState<StepId>("profile");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const [headline, setHeadline] = useState("");
  const [bio, setBio] = useState("");
  const [location, setLocation] = useState("");
  const [interests, setInterests] = useState<string[]>([]);
  const [hobbies, setHobbies] = useState<string[]>([]);
  const [lookingFor, setLookingFor] = useState<string[]>([]);
  const [likes, setLikes] = useState<string[]>([]);
  const [dislikes, setDislikes] = useState<string[]>([]);

  const [sources, setSources] = useState<PersonaSource[]>([]);
  const [linkDraft, setLinkDraft] = useState("");
  const [persona, setPersona] = useState<Persona | null>(null);

  useEffect(() => {
    if (!profile) return;
    setHeadline(profile.headline || "");
    setBio(profile.bio || "");
    setLocation(profile.location || "");
    setInterests(profile.interests || []);
    setHobbies(profile.hobbies || []);
    setLookingFor(profile.looking_for || []);
    setLikes(profile.likes || []);
    setDislikes(profile.dislikes || []);
  }, [profile]);

  useEffect(() => {
    void personaApi.sources().then(setSources).catch(() => undefined);
  }, []);

  const run = useCallback(async (action: () => Promise<void>) => {
    setBusy(true);
    setError("");
    try {
      await action();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }, []);

  const saveBasics = () =>
    run(async () => {
      await profileApi.update({ headline, bio, location });
      setStep("sources");
    });

  const saveExtras = () =>
    run(async () => {
      await profileApi.update({
        interests,
        hobbies,
        looking_for: lookingFor,
        likes,
        dislikes,
      });
      setStep("persona");
    });

  const uploadFile = (file: File) =>
    run(async () => {
      const created = await personaApi.uploadSource(file);
      setSources((current) => [...current, created]);
    });

  const addLink = () =>
    run(async () => {
      const created = await personaApi.addLink(linkDraft);
      setSources((current) => [...current, created]);
      setLinkDraft("");
    });

  const removeSource = (id: string) =>
    run(async () => {
      await personaApi.deleteSource(id);
      setSources((current) => current.filter((item) => item._id !== id));
    });

  const buildPersona = () =>
    run(async () => {
      const result = await personaApi.build();
      setPersona(result.persona);
      await refresh();
    });

  const finish = () => navigate("/feed", { replace: true });

  const stepIndex = STEPS.findIndex((item) => item.id === step);

  return (
    <div className="onboarding">
      <header className="onboarding-head">
        <div className="auth-brand">
          <span><Sparkles size={18} /></span>
          <strong>AgentCircle</strong>
        </div>
        <p>Hi {user?.display_name?.split(" ")[0] || "there"} — let's give your agent something to work with.</p>
      </header>

      <ol className="onboarding-steps">
        {STEPS.map((item, index) => (
          <li
            key={item.id}
            className={index === stepIndex ? "current" : index < stepIndex ? "done" : ""}
          >
            <span className="step-dot">{index < stepIndex ? <Check size={13} /> : index + 1}</span>
            <span className="step-text">
              <strong>{item.label}</strong>
              <small>{item.blurb}</small>
            </span>
          </li>
        ))}
      </ol>

      <section className="onboarding-panel">
        {error && (
          <p className="auth-error" role="alert">
            <TriangleAlert size={14} /> {error}
          </p>
        )}

        {step === "profile" && (
          <>
            <h2>The basics</h2>
            <p className="panel-sub">This is what other people see first.</p>
            <label className="field">
              <span>Headline</span>
              <input
                value={headline}
                onChange={(event) => setHeadline(event.target.value)}
                placeholder="Founder building onboarding analytics for B2B SaaS"
                maxLength={160}
              />
            </label>
            <label className="field">
              <span>About you</span>
              <textarea
                value={bio}
                onChange={(event) => setBio(event.target.value)}
                placeholder="A few sentences in your own words."
                rows={5}
                maxLength={2000}
              />
            </label>
            <label className="field">
              <span>Location</span>
              <input
                value={location}
                onChange={(event) => setLocation(event.target.value)}
                placeholder="San Francisco"
                maxLength={120}
              />
            </label>
            <div className="panel-actions">
              <button className="primary" onClick={saveBasics} disabled={busy}>
                Continue <ArrowRight size={15} />
              </button>
            </div>
          </>
        )}

        {step === "sources" && (
          <>
            <h2>What should your agent know?</h2>
            <p className="panel-sub">
              Upload a resume or point at your site. Your agent only ever answers from what
              you give it here — if something is missing it says so instead of guessing.
            </p>

            <div className="source-actions">
              <button className="ghost" onClick={() => fileInput.current?.click()} disabled={busy}>
                <Upload size={15} /> Upload a file
              </button>
              <input
                ref={fileInput}
                type="file"
                accept=".pdf,.docx,.txt,.md,.markdown"
                hidden
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  if (file) void uploadFile(file);
                  event.target.value = "";
                }}
              />
              <div className="link-row">
                <input
                  value={linkDraft}
                  onChange={(event) => setLinkDraft(event.target.value)}
                  placeholder="yoursite.com, LinkedIn, GitHub, a blog post…"
                  onKeyDown={(event) => {
                    if (event.key === "Enter" && linkDraft.trim()) {
                      event.preventDefault();
                      void addLink();
                    }
                  }}
                />
                <button className="ghost" onClick={addLink} disabled={busy || !linkDraft.trim()}>
                  <Link2 size={15} /> Add
                </button>
              </div>
            </div>

            <ul className="source-list">
              {sources.map((source) => (
                <li key={source._id}>
                  <span className="source-icon">
                    {source.kind === "link" ? <Link2 size={14} /> : <FileText size={14} />}
                  </span>
                  <span className="source-body">
                    <strong>{source.title}</strong>
                    <small>
                      {source.chunk_count} chunk{source.chunk_count === 1 ? "" : "s"} ·{" "}
                      {source.characters.toLocaleString()} characters
                    </small>
                  </span>
                  <button
                    className="icon-button"
                    onClick={() => removeSource(source._id)}
                    disabled={busy}
                    aria-label={`Remove ${source.title}`}
                  >
                    <Trash2 size={14} />
                  </button>
                </li>
              ))}
              {!sources.length && (
                <li className="source-empty">Nothing yet — add at least one source.</li>
              )}
            </ul>

            <div className="panel-actions">
              <button className="ghost" onClick={() => setStep("profile")}>
                <ArrowLeft size={15} /> Back
              </button>
              <button
                className="primary"
                onClick={() => setStep("extras")}
                disabled={busy || !sources.length}
              >
                Continue <ArrowRight size={15} />
              </button>
            </div>
          </>
        )}

        {step === "extras" && (
          <>
            <h2>The human parts</h2>
            <p className="panel-sub">
              A resume says what you have done. This says who you are — and it is usually what
              makes an introduction actually land.
            </p>
            <ChipInput
              label="Interests"
              values={interests}
              onChange={setInterests}
              placeholder="B2B SaaS, developer tools, typography…"
            />
            <ChipInput
              label="Hobbies"
              values={hobbies}
              onChange={setHobbies}
              placeholder="Climbing, cooking, chess…"
            />
            <ChipInput
              label="Looking for"
              hint="What a good introduction would get you right now"
              values={lookingFor}
              onChange={setLookingFor}
              placeholder="Design partners, a technical cofounder…"
            />
            <ChipInput
              label="Likes"
              values={likes}
              onChange={setLikes}
              placeholder="Direct feedback, small teams…"
            />
            <ChipInput
              label="Dislikes"
              hint="Your agent uses these to filter, not just to match"
              values={dislikes}
              onChange={setDislikes}
              placeholder="Cold pitches, unpaid trials…"
            />
            <div className="panel-actions">
              <button className="ghost" onClick={() => setStep("sources")}>
                <ArrowLeft size={15} /> Back
              </button>
              <button className="primary" onClick={saveExtras} disabled={busy}>
                Continue <ArrowRight size={15} />
              </button>
            </div>
          </>
        )}

        {step === "persona" && (
          <>
            <h2>What your agent understood</h2>
            {!persona && (
              <>
                <p className="panel-sub">
                  Your agent will read every source you added and build a persona it can answer
                  questions from. Each claim keeps a link back to where it came from.
                </p>
                <div className="panel-actions">
                  <button className="ghost" onClick={() => setStep("extras")}>
                    <ArrowLeft size={15} /> Back
                  </button>
                  <button className="primary" onClick={buildPersona} disabled={busy}>
                    {busy ? <Loader2 size={15} className="spin" /> : <Sparkles size={15} />}
                    {busy ? "Reading your sources…" : "Build my agent"}
                  </button>
                </div>
              </>
            )}

            {persona && (
              <div className="persona-result">
                {persona.extraction_mode !== "model" && (
                  <p className="persona-flag">
                    <TriangleAlert size={14} />
                    Built without a language model, so this is a thin extraction from your own
                    text. Configure an LLM key and rebuild for a full persona.
                  </p>
                )}
                {persona.headline && <p className="persona-headline">{persona.headline}</p>}
                {persona.summary && <p className="persona-summary">{persona.summary}</p>}

                {(["skills", "interests", "looking_for"] as const).map((key) =>
                  persona[key].length ? (
                    <div className="persona-group" key={key}>
                      <span className="persona-group-label">{key.replace("_", " ")}</span>
                      <div className="persona-chips">
                        {persona[key].map((item) => (
                          <span className="chip cited" key={`${key}-${item.value}`}>
                            {item.value}
                            {item.source_title && <small>{item.source_title}</small>}
                          </span>
                        ))}
                      </div>
                    </div>
                  ) : null,
                )}

                <div className="coverage">
                  <div className="coverage-bar">
                    <span style={{ width: `${Math.round(persona.coverage.score * 100)}%` }} />
                  </div>
                  <p>
                    {persona.coverage.missing.length
                      ? `Your agent still can't answer questions about ${persona.coverage.missing.join(", ")}. It will tell people that rather than make something up — you can fill these in any time.`
                      : "Your agent can answer across every area we check for."}
                  </p>
                </div>

                <div className="panel-actions">
                  <button className="ghost" onClick={buildPersona} disabled={busy}>
                    Rebuild
                  </button>
                  <button className="primary" onClick={finish}>
                    Enter AgentCircle <ArrowRight size={15} />
                  </button>
                </div>
              </div>
            )}
          </>
        )}
      </section>
    </div>
  );
}
