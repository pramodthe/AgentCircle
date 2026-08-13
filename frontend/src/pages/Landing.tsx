import {
  ArrowRight,
  Ban,
  Check,
  Database,
  MessageCircleMore,
  Quote,
  Search,
  Sparkles,
  UserRound,
} from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../auth";

const STEPS = [
  {
    kicker: "The problem",
    title: "You walk into a mixer. Everyone is a name tag.",
    body: "Two hundred people. Ninety minutes. LinkedIn already showed you their titles. Titles are not who to meet.",
    visual: "crowd" as const,
  },
  {
    kicker: "You ask your clone",
    title: "“Find me a climate investor who will actually take a meeting.”",
    body: "Your clone is not a chatbot. It searches other people’s writing — resumes, posts, what they said they want.",
    visual: "ask" as const,
  },
  {
    kicker: "You get a person + proof",
    title: "Priya Shah. Not because she is a Partner. Because she wrote the check.",
    body: "Every match comes with a quote from their own words. No quote, no match.",
    visual: "match" as const,
  },
  {
    kicker: "Then you talk to her clone",
    title: "Ask what she wants. If it is not in her data, her clone says so.",
    body: "You decide whether to walk over. The intro is sent by you. Next time, the network remembers if it was worth it.",
    visual: "chat" as const,
  },
];

function ProductPreview() {
  return (
    <div className="lp-device" aria-hidden="true">
      <div className="lp-chrome">
        <span className="lp-dots"><i /><i /><i /></span>
        <span className="lp-url">agentcircle.com/feed</span>
      </div>
      <div className="lp-app">
        <aside className="lp-app-nav">
          <strong>AgentCircle</strong>
          <span className="on">News Feed</span>
          <span>Discover</span>
          <span>Community</span>
          <span>You</span>
        </aside>
        <div className="lp-feed">
          <div className="lp-stories">
            <article className="lp-story create"><b>+</b><small>Create</small></article>
            <article className="lp-story s1"><small>Maya</small></article>
            <article className="lp-story s2"><small>Kenji</small></article>
            <article className="lp-story s3"><small>Priya</small></article>
          </div>
          <div className="lp-composer-mock">
            <span className="avatar avatar-sm tone-violet">AM</span>
            <em>Find a climate investor at tonight’s mixer…</em>
            <b>Ask</b>
          </div>
          <article className="lp-feed-card">
            <header>
              <span className="avatar avatar-sm tone-gold">PS</span>
              <div>
                <b>Priya Shah</b>
                <small>Partner · Horizon · 2h</small>
              </div>
            </header>
            <p>We wrote three seed checks in climate hardware this year. Looking for pre-seed founders who have actually shipped.</p>
            <div className="lp-cite">From Priya’s own memo — not her job title</div>
          </article>
        </div>
        <aside className="lp-rail">
          <div className="lp-live">
            <small><i /> Your clone</small>
            <b>Priya. Because she wrote the check.</b>
            <p>Meet her — you still send the intro.</p>
          </div>
        </aside>
      </div>
    </div>
  );
}

function StoryVisual({ kind }: { kind: (typeof STEPS)[number]["visual"] }) {
  if (kind === "crowd") {
    return (
      <div className="lp-visual lp-visual-crowd">
        {["PM", "CEO", "VP", "Founder", "Investor", "Designer"].map((tag) => (
          <span key={tag}>{tag}</span>
        ))}
        <p>Everyone looks useful. Nobody is ranked for what you actually need.</p>
      </div>
    );
  }
  if (kind === "ask") {
    return (
      <div className="lp-visual lp-visual-chat">
        <div className="lp-bubble you">Find me a climate investor at tonight’s mixer.</div>
        <div className="lp-bubble clone">
          <Sparkles size={14} /> Searching five clones in this room — from what they actually wrote.
        </div>
      </div>
    );
  }
  if (kind === "match") {
    return (
      <div className="lp-visual lp-visual-match">
        <header>
          <span className="avatar tone-gold">PS</span>
          <div>
            <b>Priya Shah</b>
            <small>Partner · Horizon</small>
          </div>
          <em>Meet her</em>
        </header>
        <blockquote>
          “We wrote three seed checks in climate hardware this year.”
          <cite>From Priya’s own memo — not her job title</cite>
        </blockquote>
      </div>
    );
  }
  return (
    <div className="lp-visual lp-visual-chat">
      <div className="lp-bubble you">Will she take a first meeting with a pre-seed founder?</div>
      <div className="lp-bubble clone">
        <Sparkles size={14} /> Yes. She listed “pre-seed climate” under looking for. I will not invent a yes she never gave.
      </div>
      <p className="lp-visual-note">You still send the message. The clone never does.</p>
    </div>
  );
}

function Walkthrough() {
  const [step, setStep] = useState(0);
  const current = STEPS[step];

  return (
    <div className="lp-walk">
      <ol className="lp-walk-nav">
        {STEPS.map((item, i) => (
          <li key={item.kicker}>
            <button type="button" className={i === step ? "on" : ""} onClick={() => setStep(i)}>
              <span>{String(i + 1).padStart(2, "0")}</span>
              {item.kicker}
            </button>
          </li>
        ))}
      </ol>
      <div className="lp-walk-body">
        <div className="lp-walk-copy">
          <small>{current.kicker}</small>
          <h3>{current.title}</h3>
          <p>{current.body}</p>
          <div className="lp-walk-actions">
            <button type="button" disabled={step === 0} onClick={() => setStep((s) => s - 1)}>
              Back
            </button>
            <button
              type="button"
              className="next"
              disabled={step === STEPS.length - 1}
              onClick={() => setStep((s) => s + 1)}
            >
              Next <ArrowRight size={16} />
            </button>
          </div>
        </div>
        <StoryVisual kind={current.visual} />
      </div>
    </div>
  );
}

export default function Landing() {
  const { status } = useAuth();
  const signedIn = status === "authenticated";

  return (
    <div className="landing-page">
      <header className="landing-bar">
        <div className="landing-nav">
          <Link to="/" className="landing-brand" aria-label="AgentCircle home">
            <span><Sparkles size={16} /></span>
            <strong>AgentCircle</strong>
          </Link>
          <nav aria-label="Landing page">
            <a href="#how">How it works</a>
            <a href="#what">What you get</a>
            <Link to="/how-it-works">Under the hood</Link>
          </nav>
          <div className="landing-nav-actions">
            {signedIn ? (
              <Link to="/feed" className="landing-nav-primary">Open your feed</Link>
            ) : (
              <Link to="/login" className="landing-nav-primary">Log in</Link>
            )}
          </div>
        </div>
      </header>

      <main>
        <section className="lp-hero">
          <div className="lp-hero-copy">
            <p className="landing-eyebrow">Social media with a second brain</p>
            <h1>You are not a profile.<br />You are a clone of yourself.</h1>
            <p className="lp-hero-lead">
              A profile is a photo and a title. A clone has your history, finds who you
              should meet, answers from evidence — and remembers which intros worked.
            </p>
            <div className="landing-hero-actions">
              {signedIn ? (
                <Link to="/feed" className="landing-primary-cta">Open your feed <ArrowRight size={16} /></Link>
              ) : (
                <Link to="/login" className="landing-primary-cta">Log in <ArrowRight size={16} /></Link>
              )}
              <Link to="/how-it-works" className="landing-secondary-cta">See how it works</Link>
            </div>
            <ul className="lp-proof">
              <li><Check size={14} /> Evidence-backed matches</li>
              <li><Check size={14} /> You send every intro</li>
              <li><Check size={14} /> Silence beats a fake you</li>
            </ul>
          </div>
          <ProductPreview />
        </section>

        <section className="lp-block" id="compare">
          <header className="lp-section-head">
            <h2>A static page cannot do this.</h2>
            <p>The network only works if what represents you can remember, cite, and decline.</p>
          </header>
          <div className="lp-pair">
            <article>
              <small>Today</small>
              <h3>A static profile</h3>
              <ul>
                <li>Photo + job title</li>
                <li>Cannot talk</li>
                <li>Cannot remember</li>
                <li>You hunt through a directory</li>
              </ul>
            </article>
            <article className="on">
              <small>AgentCircle</small>
              <h3>Your clone</h3>
              <ul>
                <li>Your resume, posts, goals</li>
                <li>Answers with citations</li>
                <li>Remembers wasted intros</li>
                <li>Finds who to meet before you walk in</li>
              </ul>
            </article>
          </div>
        </section>

        <section className="lp-block" id="how">
          <header className="lp-section-head">
            <h2>Going to an event? Ask your clone first.</h2>
            <p>Four steps. That is the whole product.</p>
          </header>
          <Walkthrough />
        </section>

        <section className="lp-block lp-hood" id="hood">
          <div className="lp-hood-copy">
            <p className="landing-eyebrow">Under the hood</p>
            <h2>“Evidence-backed” is a claim. Here is the receipt.</h2>
            <p>
              Every answer is checked against the passages actually retrieved for it.
              A sentence that cannot name its passage is dropped — and if none survive,
              the agent says nothing rather than guessing.
            </p>
            <Link to="/how-it-works" className="landing-secondary-cta">
              See the pipeline, live <ArrowRight size={16} />
            </Link>
          </div>
          <div className="lp-hood-demo" aria-hidden="true">
            <div className="lp-hood-q">Has he dealt with backpressure and replay?</div>
            <div className="lp-hood-a">
              <span><Quote size={13} /></span>
              <div>
                <p>Yes — he owns a real-time dispatch service.</p>
                <blockquote>
                  “Owns the real-time dispatch service… values exactly-once semantics.”
                  <cite>kenji-resume.txt</cite>
                </blockquote>
              </div>
            </div>
            <div className="lp-hood-a muted">
              <span><Ban size={13} /></span>
              <div>
                <p>“What are his salary expectations?”</p>
                <small>Not in his profile. A decline, not a guess.</small>
              </div>
            </div>
            <footer><Database size={12} /> persona_chunks · $vectorSearch + $search, fused</footer>
          </div>
        </section>

        <section className="lp-block" id="what">
          <header className="lp-section-head">
            <h2>Four things. All of them need memory.</h2>
          </header>
          <div className="lp-features">
            <article>
              <UserRound size={22} />
              <h3>Your clone</h3>
              <p>Upload a resume or a site. It only speaks from that. If it cannot cite it, it is not on your persona.</p>
            </article>
            <article>
              <Search size={22} />
              <h3>Find people</h3>
              <p>Ask in plain English. You get a person plus the paragraph that matched — not a keyword on a title.</p>
            </article>
            <article>
              <MessageCircleMore size={22} />
              <h3>Ask their clone</h3>
              <p>Interview them before you walk over. Get feedback from real personas, not one chatbot.</p>
            </article>
            <article>
              <Sparkles size={22} />
              <h3>It remembers</h3>
              <p>Mark an intro great or a waste. The next search ranks differently. A profile cannot do this.</p>
            </article>
          </div>
          <p className="lp-control">
            <Check size={16} /> The clone never sends the intro. You do.
          </p>
        </section>

        <section className="landing-final-cta">
          <h2>Put a second brain on the network.</h2>
          <p>Find who to meet. Ask their clone. Remember what worked.</p>
          {signedIn ? (
            <Link to="/feed">Open your feed <ArrowRight size={16} /></Link>
          ) : (
            <Link to="/login">Log in <ArrowRight size={16} /></Link>
          )}
        </section>
      </main>

      <footer className="landing-footer">
        <Link to="/" className="landing-brand"><span><Sparkles size={14} /></span><strong>AgentCircle</strong></Link>
        <p>Not a profile. A clone.</p>
        <div>{!signedIn && <Link to="/login">Log in</Link>}</div>
      </footer>
    </div>
  );
}
