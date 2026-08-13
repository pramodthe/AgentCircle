import { ArrowRight } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth";
import { DEMO_ACCOUNTS, DEMO_PASSWORD, initials } from "../demoAccounts";

/**
 * Prototype entry: pick a seeded person, skip the password form.
 * Still goes through the real login path so every store keeps a real user_id.
 */
export default function EnterAs() {
  const { signIn } = useAuth();
  const navigate = useNavigate();
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState("");

  const enter = async (email: string) => {
    setError("");
    setBusy(email);
    try {
      await signIn(email, DEMO_PASSWORD);
      navigate("/find", { replace: true });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not enter");
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="enter-as">
      <div className="enter-as-grid" role="list">
        {DEMO_ACCOUNTS.map((person) => {
          const first = person.name.split(" ")[0];
          const loading = busy === person.email;
          return (
            <button
              key={person.email}
              type="button"
              role="listitem"
              className="enter-as-btn"
              disabled={busy !== null}
              onClick={() => void enter(person.email)}
            >
              <span className={`avatar avatar-sm tone-${person.accent}`} aria-hidden="true">
                {initials(person.name)}
              </span>
              <span className="enter-as-meta">
                <b>{loading ? "Entering…" : first}</b>
                <small>{person.role}</small>
              </span>
              <ArrowRight size={14} className="enter-as-arrow" aria-hidden="true" />
            </button>
          );
        })}
      </div>
      {error && <p className="auth-error" role="alert">{error}</p>}
    </div>
  );
}
