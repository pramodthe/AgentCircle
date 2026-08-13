import { Sparkles } from "lucide-react";
import type { ReactNode } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import AppShell from "./AppShell";
import { useAuth } from "./auth";
import { CommunityIndex, CommunityThreadPage } from "./pages/Community";
import Connections from "./pages/Connections";
import Discover from "./pages/Discover";
import Feed from "./pages/Feed";
import InterviewPage from "./pages/Interview";
import HowItWorks from "./pages/HowItWorks";
import Landing from "./pages/Landing";
import Me from "./pages/Me";
import Messages from "./pages/Messages";
import Onboarding from "./pages/Onboarding";
import PublicProfile from "./pages/PublicProfile";
import Research from "./pages/Research";
import SignIn from "./pages/SignIn";

function Booting() {
  return (
    <div className="auth-screen">
      <div className="auth-booting">
        <Sparkles size={20} />
        <span>Waking up your agent…</span>
      </div>
    </div>
  );
}

/** Requires a session. Sends a signed-in user with no persona to onboarding first. */
function Protected({
  children,
  allowIncomplete = false,
}: {
  children: ReactNode;
  allowIncomplete?: boolean;
}) {
  const { status, onboarding } = useAuth();
  const location = useLocation();

  if (status === "loading") return <Booting />;
  if (status === "anonymous") {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  if (!allowIncomplete && onboarding && !onboarding.complete) {
    return <Navigate to="/onboarding" replace />;
  }
  return <>{children}</>;
}

function AnonymousOnly({ children }: { children: ReactNode }) {
  const { status } = useAuth();
  if (status === "loading") return <Booting />;
  if (status === "authenticated") return <Navigate to="/feed" replace />;
  return <>{children}</>;
}

export default function Root() {
  return (
    <Routes>
      <Route index element={<Landing />} />
      <Route path="/how-it-works" element={<HowItWorks />} />
      <Route path="/welcome" element={<Navigate to="/" replace />} />
      <Route path="/login" element={<AnonymousOnly><SignIn mode="login" /></AnonymousOnly>} />
      <Route path="/register" element={<AnonymousOnly><SignIn mode="register" /></AnonymousOnly>} />
      <Route
        path="/onboarding"
        element={<Protected allowIncomplete><Onboarding /></Protected>}
      />

      {/* Everything past onboarding shares one shell. */}
      <Route element={<Protected><AppShell /></Protected>}>
        <Route path="feed" element={<Feed />} />
        <Route path="find" element={<Discover />} />
        <Route path="community" element={<CommunityIndex />} />
        <Route path="community/:postId" element={<CommunityThreadPage />} />
        <Route path="messages" element={<Messages />} />
        <Route path="messages/:userId" element={<Messages />} />
        <Route path="connections" element={<Connections />} />
        <Route path="me" element={<Me />} />
        <Route path="me/:tab" element={<Me />} />
        <Route path="agent" element={<Navigate to="/me#documents" replace />} />
        <Route path="profile" element={<Navigate to="/me" replace />} />
        <Route path="profile/edit" element={<Navigate to="/me?edit=1" replace />} />
        <Route path="interview/:subjectId" element={<InterviewPage />} />
        <Route path="research/:subjectId" element={<Research />} />
        <Route path="u/:handle" element={<PublicProfile />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
