import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { auth as authApi, loadStoredToken, setAuthToken, setUnauthorizedHandler } from "./api";
import type { AuthUser, MeResponse, OnboardingState, Persona, UserProfile } from "./types";

interface AuthState {
  status: "loading" | "authenticated" | "anonymous";
  user?: AuthUser;
  profile?: UserProfile | null;
  persona?: Persona | null;
  onboarding?: OnboardingState;
}

interface AuthContextValue extends AuthState {
  signIn: (email: string, password: string) => Promise<void>;
  signUp: (email: string, password: string, displayName: string) => Promise<void>;
  signOut: () => void;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({ status: "loading" });

  const applySession = useCallback((payload: MeResponse) => {
    setState({
      status: "authenticated",
      user: payload.user,
      profile: payload.profile,
      persona: payload.persona,
      onboarding: payload.onboarding,
    });
  }, []);

  const signOut = useCallback(() => {
    setAuthToken(null);
    setState({ status: "anonymous" });
  }, []);

  const refresh = useCallback(async () => {
    if (!loadStoredToken()) {
      setState({ status: "anonymous" });
      return;
    }
    try {
      applySession(await authApi.me());
    } catch {
      // A stored token that the API rejects is worse than no token.
      setAuthToken(null);
      setState({ status: "anonymous" });
    }
  }, [applySession]);

  const signIn = useCallback(
    async (email: string, password: string) => {
      const result = await authApi.login(email, password);
      setAuthToken(result.access_token);
      applySession(await authApi.me());
    },
    [applySession],
  );

  const signUp = useCallback(
    async (email: string, password: string, displayName: string) => {
      const result = await authApi.register(email, password, displayName);
      setAuthToken(result.access_token);
      applySession(await authApi.me());
    },
    [applySession],
  );

  useEffect(() => {
    setUnauthorizedHandler(() => {
      setAuthToken(null);
      setState({ status: "anonymous" });
    });
    return () => setUnauthorizedHandler(null);
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const value = useMemo<AuthContextValue>(
    () => ({ ...state, signIn, signUp, signOut, refresh }),
    [state, signIn, signUp, signOut, refresh],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside <AuthProvider>");
  return value;
}
