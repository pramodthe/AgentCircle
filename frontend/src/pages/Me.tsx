import { TriangleAlert } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Navigate, useLocation, useParams, useSearchParams } from "react-router-dom";
import { communityApi, mediaApi, personaApi, profileApi } from "../api";
import { useAuth } from "../auth";
import AgentDocuments from "../components/AgentDocuments";
import AgentMemory from "../components/AgentMemory";
import AgentPermissions from "../components/AgentPermissions";
import Photos from "../components/Photos";
import { ProfileView } from "../components/ProfileView";
import EditProfile from "./EditProfile";
import type { GapDemand, MemberPhoto, Persona, PersonaSource, PublicProfile as PublicProfileData } from "../types";

const TAB_HASH: Record<string, string> = {
  about: "about",
  photos: "photos",
  knowledge: "documents",
  permissions: "permissions",
};

/**
 * One LinkedIn-style page: appearance, claims, documents and permissions.
 * `/u/:handle` is the public face of the same object.
 */
export default function Me() {
  const { user, refresh } = useAuth();
  const { tab: tabParam } = useParams();
  const location = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();

  const [data, setData] = useState<PublicProfileData>();
  const [persona, setPersona] = useState<Persona | null>(null);
  const [sources, setSources] = useState<PersonaSource[]>([]);
  const [demand, setDemand] = useState<GapDemand>();
  const [photos, setPhotos] = useState<MemberPhoto[]>([]);
  const [error, setError] = useState("");
  const [docError, setDocError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);

  const editing = searchParams.get("edit") === "1";

  const loadProfile = useCallback(async () => {
    if (!user?.handle) return;
    setError("");
    setData(await profileApi.public(user.handle));
  }, [user?.handle]);

  const loadAgent = useCallback(async () => {
    const [personaRow, demandRow] = await Promise.all([
      personaApi.get(),
      communityApi.gapDemand(),
    ]);
    setPersona(personaRow.persona);
    setSources(personaRow.sources);
    setDemand(demandRow);
  }, []);

  const loadPhotos = useCallback(async (userId: string) => {
    setPhotos(await mediaApi.forUser(userId).catch(() => []));
  }, []);

  useEffect(() => {
    void loadProfile().catch((caught) => setError(caught.message));
    void loadAgent().catch((caught) => setDocError(caught.message));
  }, [loadProfile, loadAgent]);

  useEffect(() => {
    if (data?.user._id) void loadPhotos(data.user._id);
  }, [data?.user._id, loadPhotos]);

  useEffect(() => {
    const hash = location.hash.replace("#", "") || (tabParam ? TAB_HASH[tabParam] : "");
    if (!hash || !data) return;
    const node = document.getElementById(hash);
    if (node) node.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [location.hash, tabParam, data]);

  const run = async (action: () => Promise<unknown>, message?: string) => {
    setBusy(true);
    setDocError("");
    setNotice("");
    try {
      await action();
      if (message) setNotice(message);
      await loadAgent();
    } catch (caught) {
      setDocError(caught instanceof Error ? caught.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  };

  const openEdit = () => {
    const next = new URLSearchParams(searchParams);
    next.set("edit", "1");
    setSearchParams(next, { replace: true });
  };

  const closeEdit = () => {
    const next = new URLSearchParams(searchParams);
    next.delete("edit");
    setSearchParams(next, { replace: true });
  };

  if (tabParam) {
    const hash = TAB_HASH[tabParam];
    return <Navigate to={hash ? `/me#${hash}` : "/me"} replace />;
  }

  if (error && !data) return <p className="auth-error"><TriangleAlert size={14} /> {error}</p>;
  if (!data) return <p className="thread-loading">Loading profile…</p>;

  return (
    <>
      <ProfileView
        data={data}
        photos={photos}
        isMe
        owner
        persona={persona}
        onEdit={openEdit}
        documents={
          <AgentDocuments
            sources={sources}
            demand={demand}
            busy={busy}
            error={docError}
            notice={notice}
            onUpload={(file) => void run(() => personaApi.uploadSource(file), "Added.")}
            onAddLink={(url) => void run(() => personaApi.addLink(url), "Added.")}
            onDelete={(id) => void run(() => personaApi.deleteSource(id), "Removed.")}
            onRebuild={() => void run(async () => {
              await personaApi.build();
              await refresh();
            }, "Rebuilt from your documents.")}
            onResolveGaps={(ids) => void run(() => communityApi.resolveGaps(ids))}
          />
        }
        memory={<AgentMemory />}
        permissions={<AgentPermissions />}
        photoComposer={<Photos composer onChanged={() => { if (data.user._id) void loadPhotos(data.user._id); }} />}
        onRemovePhoto={(id) => {
          void mediaApi.remove(id).then(() => {
            if (data.user._id) return loadPhotos(data.user._id);
          }).catch((caught) => {
            setDocError(caught instanceof Error ? caught.message : "Could not remove photo");
          });
        }}
      />
      {editing && (
        <EditProfile
          embedded
          onClose={closeEdit}
          onSaved={async () => {
            await Promise.all([loadProfile(), loadAgent(), refresh()]);
            closeEdit();
          }}
        />
      )}
    </>
  );
}
