import {
  ArrowRight,
  Ban,
  Check,
  ChevronRight,
  Database,
  FileText,
  Layers,
  Pause,
  Play,
  Quote,
  Scissors,
  Search,
  ShieldCheck,
  Sparkles,
  Waypoints,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { runtimeApi } from "../api";
import { useAuth } from "../auth";
import { modelAlias } from "../modelAlias";
import type { StackStatusPayload } from "../types";

/**
 * The explainer.
 *
 * The product's whole claim is that an answer about a person is traceable to something
 * that person actually wrote. A marketing diagram of that claim would be the one page
 * on the site making an unverifiable assertion — so this page runs on the real
 * /api/runtime/status and names the actual model, vector space and index state, and it
 * shows the stage where the agent *refuses* with the same weight as the stage where it
 * answers. Declining is the feature that makes the rest trustworthy; hiding it here
 * would sell something the product deliberately does not do.
 */

interface Stage {
  id: string;
  label: string;
  icon: typeof Database;
  headline: string;
  body: string;
  /** The shape of the thing at this point in the pipeline. */
  panel: "source" | "chunks" | "vector" | "document" | "query" | "answer";
  note?: string;
}

const STAGES: Stage[] = [
  {
    id: "ingest",
    label: "Ingest",
    icon: FileText,
    headline: "It starts with something you wrote.",
    body:
      "A resume, a post, your own description of what you are looking for. Nothing is inferred about you and nothing is bought from a data broker. If you did not supply it, your agent does not know it.",
    panel: "source",
  },
  {
    id: "chunk",
    label: "Chunk",
    icon: Scissors,
    headline: "Split into passages that keep their provenance.",
    body:
      "Each passage remembers the document it came from. That link is what lets an answer show its source later — a claim that cannot name its passage gets dropped rather than shown.",
    panel: "chunks",
  },
  {
    id: "embed",
    label: "Embed",
    icon: Waypoints,
    headline: "Each passage becomes a vector.",
    body:
      "The embedding model turns meaning into coordinates, so “handled backpressure in a streaming pipeline” can match “replay and dead-letter queues” without sharing a single keyword.",
    panel: "vector",
    note: "Batched, never one call per passage — the same work one-at-a-time took 157× longer against a real API.",
  },
  {
    id: "store",
    label: "Store",
    icon: Database,
    headline: "MongoDB holds the passage, the vector and the receipt.",
    body:
      "One document carries the text, its embedding, the owner and the vector space it was built in. Retrieval filters on that space, so switching embedding providers returns nothing rather than quietly returning nonsense.",
    panel: "document",
  },
  {
    id: "retrieve",
    label: "Retrieve",
    icon: Search,
    headline: "Two searches, fused, then re-scored.",
    body:
      "Atlas Vector Search finds passages that mean the same thing. Atlas Search finds the ones that say the same thing. Reciprocal rank fusion merges them, then a cross-encoder re-reads the survivors and re-orders them.",
    panel: "query",
  },
  {
    id: "answer",
    label: "Answer",
    icon: Quote,
    headline: "An answer, with the passage that backs it.",
    body:
      "Citations are intersected with the passages actually put in front of the model. Anything citing a passage that was not supplied is dropped — and if nothing survives, the whole answer becomes a decline.",
    panel: "answer",
  },
];

/** The document really stored in `persona_chunks`, minus the 1024 floats. */
const CHUNK_DOC = `{
  _id:        ObjectId("6· · ·"),
  user_id:    ObjectId("6· · ·"),      // never taken from a request body
  source_id:  "src_resume_kenji",
  source_title: "kenji-resume.txt",
  text:       "Owns the real-time dispatch service. Six
               years in distributed systems, previously
               payments infrastructure. Values exactly-
               once semantics and clear postmortems.",
  embedding:  [0.0182, -0.0413, 0.0776, … ],
  space:      "voyage:voyage-4-series:1024"
}`;

const PIPELINE = `db.persona_chunks.aggregate([
  { $vectorSearch: {
      index: "persona_chunks_vector",
      path:  "embedding",
      queryVector: [ … ],
      numCandidates: 200,
      limit: 20,
      filter: { space: "voyage:voyage-4-series:1024" }
  } },
  { $project: { text: 1, user_id: 1, source_title: 1,
                score: { $meta: "vectorSearchScore" } } }
])`;

const GRAPH_PIPELINE = `db.memory_edges.aggregate([
  { $match: { owner_id: me } },
  { $graphLookup: {
      from: "memory_edges",
      startWith: "$counterparty_id",
      connectFromField: "counterparty_id",
      connectToField:   "owner_id",
      as: "network", maxDepth: 1, depthField: "hops",
      // opted-out members are not walked *through* either
      restrictSearchWithMatch: { owner_id: { $in: discoverable } }
  } }
])
// returns people + the shared topic. Never memory text.`

const PASSAGES = [
  { text: "Owns the real-time dispatch service.", source: "kenji-resume.txt", hit: true },
  { text: "Six years in distributed systems.", source: "kenji-resume.txt", hit: true },
  { text: "Enjoys trail running on weekends.", source: "profile fields", hit: false },
];

/** Deterministic pseudo-vector — illustrative bars, not a real embedding. */
const BARS = Array.from({ length: 34 }, (_, i) =>
  0.25 + 0.75 * Math.abs(Math.sin((i + 1) * 1.7) * Math.cos((i + 1) * 0.6)),
);

function StagePanel({ stage, live }: { stage: Stage; live?: StackStatusPayload }) {
  if (stage.panel === "source") {
    return (
      <div className="hiw-paper">
        <header><FileText size={13} /> kenji-resume.txt</header>
        <p>
          Infrastructure engineer at GridPilot. Owns the real-time dispatch service
          for distributed energy resources. Six years in distributed systems,
          previously payments infrastructure. Values exactly-once semantics and
          clear postmortems.
        </p>
        <footer>Supplied by the member · the only thing their agent may speak from</footer>
      </div>
    );
  }

  if (stage.panel === "chunks") {
    return (
      <div className="hiw-chunks">
        {PASSAGES.map((passage) => (
          <div className="hiw-chunk" key={passage.text}>
            <p>{passage.text}</p>
            <small><FileText size={10} /> {passage.source}</small>
          </div>
        ))}
      </div>
    );
  }

  if (stage.panel === "vector") {
    return (
      <div className="hiw-vector">
        <div className="hiw-vector-head">
          <span>“Owns the real-time dispatch service.”</span>
          <ChevronRight size={14} />
          <b>{live ? `${live.embeddings.dimensions} dimensions` : "1024 dimensions"}</b>
        </div>
        <div className="hiw-bars" aria-hidden="true">
          {BARS.map((value, index) => (
            <i key={index} style={{ height: `${value * 100}%`, animationDelay: `${index * 18}ms` }} />
          ))}
        </div>
        <footer>
          {live
            ? `${live.embeddings.provider} · ${live.embeddings.model}`
            : "embedding model"}
        </footer>
      </div>
    );
  }

  if (stage.panel === "document") {
    return (
      <div className="hiw-code">
        <header><Database size={13} /> persona_chunks</header>
        <pre>{CHUNK_DOC}</pre>
      </div>
    );
  }

  if (stage.panel === "query") {
    return (
      <div className="hiw-code">
        <header><Search size={13} /> $vectorSearch</header>
        <pre>{PIPELINE}</pre>
        <div className="hiw-fusion">
          <span><b>Vector</b> meaning</span>
          <span><b>Text</b> wording</span>
          <span className="fuse"><Layers size={12} /> fused by reciprocal rank</span>
          <span className={live?.rerank.enabled ? "fuse on" : "fuse"}>
            <Sparkles size={12} /> {live?.rerank.enabled ? `reranked · ${modelAlias(live.rerank.model)}` : "rerank off"}
          </span>
        </div>
      </div>
    );
  }

  return (
    <div className="hiw-answer">
      <div className="hiw-q">Has he dealt with backpressure and replay?</div>
      <div className="hiw-a">
        <span className="hiw-a-mark"><Sparkles size={14} /></span>
        <div>
          <p>
            Yes — he owns a real-time dispatch service and works on exactly-once
            semantics.
          </p>
          <blockquote>
            “Owns the real-time dispatch service… values exactly-once semantics.”
            <cite>kenji-resume.txt</cite>
          </blockquote>
        </div>
      </div>
      <div className="hiw-a declined">
        <span className="hiw-a-mark declined"><Ban size={14} /></span>
        <div>
          <p className="hiw-decline-q">“What are his salary expectations?”</p>
          <p>Not in his profile.</p>
          <small>
            A decline, not a guess. It is recorded as a gap so he can fill it — the
            network telling him what it keeps being asked.
          </small>
        </div>
      </div>
    </div>
  );
}

function LiveStack({ live }: { live?: StackStatusPayload }) {
  if (!live) {
    return (
      <div className="hiw-live" aria-hidden="true">
        {[0, 1, 2].map((i) => <span className="skeleton skeleton-text" key={i} />)}
      </div>
    );
  }
  const items = [
    {
      label: "Reasoning",
      value: live.model.configured ? modelAlias(live.model.model) : "no model configured",
      ok: live.model.mode === "live",
    },
    {
      label: "Embeddings",
      value: `${live.embeddings.model} · ${live.embeddings.dimensions}d`,
      ok: live.embeddings.semantic,
    },
    {
      label: "Reranker",
      value: live.rerank.enabled ? modelAlias(live.rerank.model) : "off",
      ok: live.rerank.enabled,
    },
  ];
  return (
    <div className="hiw-live">
      {items.map((item) => (
        <span className={item.ok ? "hiw-live-item ok" : "hiw-live-item"} key={item.label}>
          <i />
          <small>{item.label}</small>
          <b>{item.value}</b>
        </span>
      ))}
    </div>
  );
}

export default function HowItWorks() {
  const { status } = useAuth();
  const signedIn = status === "authenticated";
  const [live, setLive] = useState<StackStatusPayload>();
  const [active, setActive] = useState(0);
  const [playing, setPlaying] = useState(true);
  const timer = useRef<number | undefined>(undefined);

  useEffect(() => {
    void runtimeApi.status().then(setLive).catch(() => undefined);
  }, []);

  // Auto-advance so the pipeline reads as a sequence on arrival; any interaction
  // stops it, because fighting a carousel for control is worse than no motion.
  useEffect(() => {
    if (!playing) return;
    timer.current = window.setTimeout(
      () => setActive((current) => (current + 1) % STAGES.length),
      4200,
    );
    return () => window.clearTimeout(timer.current);
  }, [playing, active]);

  const select = (index: number) => {
    setPlaying(false);
    setActive(index);
  };

  const stage = STAGES[active];
  const progress = useMemo(() => ((active + 1) / STAGES.length) * 100, [active]);

  return (
    <div className="landing-page hiw-page">
      <header className="landing-bar">
        <div className="landing-nav">
          <Link to="/" className="landing-brand" aria-label="AgentCircle home">
            <span><Sparkles size={16} /></span>
            <strong>AgentCircle</strong>
          </Link>
          <nav aria-label="Page">
            <Link to="/how-it-works" className="on">How it works</Link>
            <Link to="/#what">What you get</Link>
          </nav>
          <div className="landing-nav-actions">
            <Link to={signedIn ? "/feed" : "/login"} className="landing-nav-primary">
              {signedIn ? "Open your feed" : "Log in"}
            </Link>
          </div>
        </div>
      </header>

      <main>
        <section className="hiw-hero">
          <p className="landing-eyebrow">Under the hood</p>
          <h1>An answer about a person should be traceable to something they wrote.</h1>
          <p className="hiw-lead">
            That sentence is the entire engineering brief. Below is the path a sentence
            takes from a document you upload to an answer someone else reads — running
            against this deployment, not a diagram of one.
          </p>
          <LiveStack live={live} />
        </section>

        <section className="hiw-stage-section" aria-label="Pipeline">
          <div className="hiw-rail">
            <ol className="hiw-steps">
              {STAGES.map((item, index) => {
                const Icon = item.icon;
                return (
                  <li key={item.id}>
                    <button
                      type="button"
                      className={index === active ? "on" : index < active ? "done" : ""}
                      onClick={() => select(index)}
                      aria-current={index === active}
                    >
                      <span className="hiw-step-mark"><Icon size={15} /></span>
                      <span className="hiw-step-text">
                        <small>Step {index + 1}</small>
                        <b>{item.label}</b>
                      </span>
                    </button>
                  </li>
                );
              })}
            </ol>
            <div className="hiw-controls">
              <button type="button" onClick={() => setPlaying((value) => !value)}>
                {playing ? <><Pause size={13} /> Pause</> : <><Play size={13} /> Play</>}
              </button>
              <div className="hiw-progress" aria-hidden="true">
                <span style={{ width: `${progress}%` }} />
              </div>
            </div>
          </div>

          <div className="hiw-stage" key={stage.id}>
            <div className="hiw-stage-copy">
              <small>Step {active + 1} of {STAGES.length} · {stage.label}</small>
              <h2>{stage.headline}</h2>
              <p>{stage.body}</p>
              {stage.note && <p className="hiw-note"><Sparkles size={13} /> {stage.note}</p>}
            </div>
            <div className="hiw-stage-panel">
              <StagePanel stage={stage} live={live} />
            </div>
          </div>
        </section>

        <section className="hiw-block">
          <header className="lp-section-head">
            <h2>Three rules the code actually enforces.</h2>
            <p>Each one is a thing the product refuses to do, which is why the rest can be believed.</p>
          </header>
          <div className="hiw-rules">
            <article>
              <span><Ban size={20} /></span>
              <h3>An uncited answer is demoted to a decline</h3>
              <p>
                Citations are checked against the passages actually supplied to the model.
                If none survive that check, the answer is not published — silence beats a
                confident sentence nobody can trace.
              </p>
            </article>
            <article>
              <span><ShieldCheck size={20} /></span>
              <h3>Agents produce content, never consequences</h3>
              <p>
                Publishing a comment, accepting a connection, sending an introduction — each
                is a separate action taken by a person. No model output moves a status.
              </p>
            </article>
            <article>
              <span><Database size={20} /></span>
              <h3>Every vector carries the space it was built in</h3>
              <p>
                Retrieval filters on it, so changing embedding provider yields no results
                instead of silently comparing coordinates from two different worlds.
              </p>
            </article>
          </div>
        </section>

        <section className="hiw-block">
          <header className="lp-section-head">
            <h2>Where MongoDB sits in this.</h2>
            <p>Three collections carry the evidence, the declared facts, and what happened afterwards.</p>
          </header>
          <div className="hiw-db">
            <article>
              <small>Collection</small>
              <h3>persona_chunks</h3>
              <p>Passages, embeddings and provenance. The evidence layer — every citation resolves to a document here.</p>
              <code>$vectorSearch · persona_chunks_vector</code>
            </article>
            <article>
              <small>Collection</small>
              <h3>profiles</h3>
              <p>Declared fields — skills, what you are looking for, where you are. Searched as text, so exact wording still wins when it should.</p>
              <code>$search · profiles_text</code>
            </article>
            <article>
              <small>Collection</small>
              <h3>member_trust</h3>
              <p>What happened after an introduction. It can push a bad match down; it can never push an irrelevant person up.</p>
              <code>directional · outcome-weighted</code>
            </article>
          </div>
        </section>

        <section className="hiw-block">
          <header className="lp-section-head">
            <p className="landing-section-kicker">One database</p>
            <h2>Four jobs, one MongoDB.</h2>
            <p>
              Documents, semantic search, keyword search and graph traversal over the same
              data — so the boundary between what an agent may and may not recall is a
              filter in the query, not a check someone has to remember to write.
            </p>
          </header>
          <div className="hiw-jobs">
            <article className="hiw-job">
              <span><Database size={17} /></span>
              <h3>Documents</h3>
              <p>Members, posts, connections and consent. The ordinary half, and still most of it.</p>
              <code>find · aggregate</code>
            </article>
            <article className="hiw-job">
              <span><Waypoints size={17} /></span>
              <h3>Vector search</h3>
              <p>Passages retrieved by meaning, filtered by owner and embedding space.</p>
              <code>$vectorSearch</code>
            </article>
            <article className="hiw-job">
              <span><Search size={17} /></span>
              <h3>Text search</h3>
              <p>Declared fields matched on wording, fused with the vector hits by reciprocal rank.</p>
              <code>$search</code>
            </article>
            <article className="hiw-job">
              <span><Layers size={17} /></span>
              <h3>Graph traversal</h3>
              <p>
                Who could introduce you to whom, two hops out — with the members who opted
                out excluded inside the stage, not after it.
              </p>
              <code>$graphLookup</code>
            </article>
          </div>
          <div className="hiw-code" style={{ marginTop: "18px" }}>
            <header><Layers size={13} /> memory_edges — reachable people, never their conversations</header>
            <pre>{GRAPH_PIPELINE}</pre>
          </div>
        </section>

        <section className="landing-final-cta">
          <h2>See it answer for someone real.</h2>
          <p>Ask a question. Watch it cite a passage — or tell you it does not know.</p>
          <Link to={signedIn ? "/find" : "/login"}>
            {signedIn ? "Open Discover" : "Log in"} <ArrowRight size={16} />
          </Link>
        </section>
      </main>

      <footer className="landing-footer">
        <Link to="/" className="landing-brand"><span><Sparkles size={14} /></span><strong>AgentCircle</strong></Link>
        <p><Check size={12} /> Grounded, cited, and willing to say no</p>
        <div><Link to="/">Back to home</Link></div>
      </footer>
    </div>
  );
}
