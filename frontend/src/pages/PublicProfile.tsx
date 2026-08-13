import { TriangleAlert } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { mediaApi, profileApi, socialApi } from "../api";
import { useAuth } from "../auth";
import { ProfileView } from "../components/ProfileView";
import type { MemberPhoto, PublicProfile as PublicProfileData, SocialConnection } from "../types";

export default function PublicProfile() {
  const { handle = "" } = useParams();
  const { user } = useAuth();
  const [data, setData] = useState<PublicProfileData>();
  const [photos, setPhotos] = useState<MemberPhoto[]>([]);
  const [connection, setConnection] = useState<SocialConnection | { status: "none" }>();
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void profileApi.public(handle).then(setData).catch((caught) => setError(caught.message));
  }, [handle]);

  useEffect(() => {
    if (!data?.user._id) return;
    void mediaApi.forUser(data.user._id).then(setPhotos).catch(() => setPhotos([]));
    if (user?._id !== data.user._id) {
      void socialApi.status(data.user._id).then(setConnection).catch(() => setConnection({ status: "none" }));
    }
  }, [data?.user._id, user?._id]);

  const connect = async () => {
    if (!data) return;
    setBusy(true);
    setError("");
    try {
      const row = await socialApi.connect(data.user._id, "", "direct");
      setConnection(row);
      setNotice(row.status === "accepted" ? "You are connected." : "Connection request sent.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not send connection request");
    } finally {
      setBusy(false);
    }
  };

  if (error && !data) return <div className="thread"><p className="auth-error"><TriangleAlert size={14} /> {error}</p><Link to="/find" className="ghost small">Back to Discover</Link></div>;
  if (!data) return <p className="thread-loading">Loading profile…</p>;
  return <ProfileView data={data} photos={photos} isMe={user?._id === data.user._id} connection={connection} busy={busy} notice={notice} error={error} onConnect={() => void connect()} />;
}
