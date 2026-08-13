import { ShieldCheck, Sparkles, Users } from "lucide-react";
import { Link } from "react-router-dom";
import EnterAs from "../components/EnterAs";

/** Prototype login — pick a seeded demo person. No password form. */
export default function SignIn({ mode }: { mode: "login" | "register" }) {
  // Register stays routed for bookmarks, but demos use the person picker.
  void mode;

  return (
    <div className="auth-social-page">
      <header className="auth-social-header">
        <Link to="/" className="auth-brand">
          <span><Sparkles size={18} /></span>
          <strong>AgentCircle</strong>
        </Link>
        <span className="auth-trust"><ShieldCheck size={14} /> Prototype login — default demo users</span>
      </header>

      <main className="auth-social-grid">
        <section className="auth-social-hero">
          <div className="auth-live-pill"><i /> Live builder network</div>
          <div className="auth-floating-person person-one"><span>MC</span><b>Maya</b></div>
          <div className="auth-floating-person person-two"><span>KT</span><b>Kenji</b></div>
          <div className="auth-story-preview">
            <header><b>Stories</b><CameraMark /></header>
            <div><span /><span /><span /></div>
          </div>
          <div className="auth-social-copy">
            <span>AI SOCIAL NETWORKING FOR BUILDERS</span>
            <h1>Meet people like a social app. Get introduced by your agent.</h1>
            <p>Browse what founders are building, follow their stories, and let grounded agents find the warmest path to a real conversation.</p>
          </div>
        </section>

        <section className="auth-card auth-social-card">
          <span className="auth-card-kicker">LOG IN</span>
          <h1>Enter as someone</h1>
          <p className="auth-sub">Ten featured logins — one tap, no password. Forty more members are already in the network.</p>
          <EnterAs />
        </section>
      </main>
    </div>
  );
}

function CameraMark() {
  return <span className="camera-mark"><Users size={13} /></span>;
}
