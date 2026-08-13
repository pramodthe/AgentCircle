"""Minimal Streamlit UI for exercising the AgentCircle FastAPI backend."""

from __future__ import annotations

import json
from typing import Any

import httpx
import streamlit as st

DEFAULT_BASE = "http://localhost:8000"


def init_state() -> None:
    defaults: dict[str, Any] = {
        "base_url": DEFAULT_BASE,
        "token": "",
        "user": None,
        "last_response": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def client() -> httpx.Client:
    headers: dict[str, str] = {"Accept": "application/json"}
    token = st.session_state.token
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return httpx.Client(
        base_url=st.session_state.base_url.rstrip("/"),
        headers=headers,
        timeout=60.0,
    )


def show_result(label: str, response: httpx.Response) -> None:
    try:
        body: Any = response.json()
    except Exception:
        body = response.text or None

    payload = {
        "label": label,
        "status_code": response.status_code,
        "ok": response.is_success,
        "body": body,
    }
    st.session_state.last_response = payload

    if response.is_success:
        st.success(f"{label} → {response.status_code}")
    else:
        st.error(f"{label} → {response.status_code}")
    st.json(body if body is not None else {"raw": response.text})


def request(
    method: str,
    path: str,
    *,
    label: str | None = None,
    json_body: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
    files: Any = None,
    data: dict[str, Any] | None = None,
) -> httpx.Response | None:
    label = label or f"{method} {path}"
    try:
        with client() as http:
            response = http.request(
                method,
                path,
                json=json_body,
                params=params,
                files=files,
                data=data,
            )
    except httpx.HTTPError as exc:
        st.error(f"{label} failed: {exc}")
        return None
    show_result(label, response)
    return response


def sidebar() -> None:
    with st.sidebar:
        st.header("Connection")
        st.session_state.base_url = st.text_input(
            "API base URL",
            value=st.session_state.base_url,
        )
        token = st.text_input(
            "Bearer token",
            value=st.session_state.token,
            type="password",
            help="Filled automatically after login/register.",
        )
        st.session_state.token = token.strip()

        if st.session_state.user:
            user = st.session_state.user
            st.caption(
                f"Signed in as **{user.get('display_name') or user.get('email')}**"
                f" (`{user.get('handle') or user.get('_id')}`)"
            )
            if st.button("Sign out", use_container_width=True):
                st.session_state.token = ""
                st.session_state.user = None
                st.rerun()

        st.divider()
        st.caption("Start the API first:")
        st.code("cd backend && uv run uvicorn app.main:app --reload --port 8000", language="bash")


def page_health() -> None:
    st.subheader("Health & runtime")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("GET /health", use_container_width=True):
            request("GET", "/health")
    with c2:
        if st.button("GET /api/runtime/status", use_container_width=True):
            request("GET", "/api/runtime/status")


def page_auth() -> None:
    st.subheader("Auth")
    tab_login, tab_register, tab_me = st.tabs(["Login", "Register", "Me"])

    with tab_login:
        with st.form("login"):
            email = st.text_input("Email", value="maya@example.com")
            password = st.text_input("Password", type="password", value="password12")
            submitted = st.form_submit_button("Login")
        if submitted:
            response = request(
                "POST",
                "/api/auth/login",
                json_body={"email": email, "password": password},
            )
            if response is not None and response.is_success:
                data = response.json()
                st.session_state.token = data.get("access_token", "")
                st.session_state.user = data.get("user")
                st.rerun()

    with tab_register:
        with st.form("register"):
            email = st.text_input("Email")
            password = st.text_input("Password (≥8 chars)", type="password")
            display_name = st.text_input("Display name")
            handle = st.text_input("Handle (optional)")
            submitted = st.form_submit_button("Register")
        if submitted:
            body: dict[str, Any] = {
                "email": email,
                "password": password,
                "display_name": display_name,
            }
            if handle.strip():
                body["handle"] = handle.strip()
            response = request("POST", "/api/auth/register", json_body=body)
            if response is not None and response.is_success:
                data = response.json()
                st.session_state.token = data.get("access_token", "")
                st.session_state.user = data.get("user")
                st.rerun()

    with tab_me:
        if st.button("GET /api/auth/me", use_container_width=True):
            response = request("GET", "/api/auth/me")
            if response is not None and response.is_success:
                st.session_state.user = response.json().get("user")


def page_profile() -> None:
    st.subheader("Profile")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("GET /api/profile", use_container_width=True):
            request("GET", "/api/profile")
    with c2:
        handle = st.text_input("Public handle", key="public_handle")
        if st.button("GET /api/profile/{handle}", use_container_width=True):
            if handle.strip():
                request("GET", f"/api/profile/{handle.strip()}")
            else:
                st.warning("Enter a handle")

    with st.form("patch_profile"):
        st.markdown("**PATCH /api/profile** (leave blank to skip)")
        display_name = st.text_input("display_name")
        headline = st.text_input("headline")
        bio = st.text_area("bio")
        location = st.text_input("location")
        submitted = st.form_submit_button("Patch profile")
    if submitted:
        body = {
            k: v
            for k, v in {
                "display_name": display_name,
                "headline": headline,
                "bio": bio,
                "location": location,
            }.items()
            if v.strip()
        }
        if not body:
            st.warning("Fill at least one field")
        else:
            request("PATCH", "/api/profile", json_body=body)


def page_persona() -> None:
    st.subheader("Persona")
    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("GET /api/persona", use_container_width=True):
            request("GET", "/api/persona")
        if st.button("GET sources", use_container_width=True):
            request("GET", "/api/persona/sources")
    with c2:
        if st.button("Build persona", use_container_width=True):
            request("POST", "/api/persona/build", params={"rebuild": "false"})
        if st.button("Rebuild persona", use_container_width=True):
            request("POST", "/api/persona/build", params={"rebuild": "true"})
    with c3:
        if st.button("Lint", use_container_width=True):
            request("GET", "/api/persona/lint")
        if st.button("Learning log", use_container_width=True):
            request("GET", "/api/persona/log", params={"limit": 50})

    with st.form("persona_link"):
        url = st.text_input("Source URL")
        submitted = st.form_submit_button("POST /api/persona/sources/link")
    if submitted and url.strip():
        request("POST", "/api/persona/sources/link", json_body={"url": url.strip()})

    uploaded = st.file_uploader(
        "Upload source (.pdf .docx .txt .md)",
        type=["pdf", "docx", "txt", "md", "markdown"],
    )
    if uploaded is not None and st.button("POST /api/persona/sources/upload"):
        request(
            "POST",
            "/api/persona/sources/upload",
            files={"file": (uploaded.name, uploaded.getvalue(), uploaded.type or "application/octet-stream")},
        )

    q = st.text_input("Search your chunks (min 3 chars)", key="persona_q")
    if st.button("GET /api/persona/search") and q.strip():
        request("GET", "/api/persona/search", params={"q": q.strip(), "limit": 6})


def page_discover() -> None:
    st.subheader("Discovery")
    if st.button("GET /api/discover/status"):
        request("GET", "/api/discover/status")

    with st.form("discover"):
        query = st.text_area("Query (8–500 chars)", height=80)
        limit = st.slider("Limit", 1, 25, 8)
        min_match = st.slider("Min match %", 0, 100, 50)
        submitted = st.form_submit_button("POST /api/discover")
    if submitted:
        request(
            "POST",
            "/api/discover",
            json_body={
                "query": query,
                "limit": limit,
                "min_match_percent": min_match,
            },
        )


def page_community() -> None:
    st.subheader("Community")
    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("List posts", use_container_width=True):
            request("GET", "/api/community/posts")
    with c2:
        if st.button("Pending comments", use_container_width=True):
            request("GET", "/api/community/pending")
    with c3:
        if st.button("Gaps / demand", use_container_width=True):
            request("GET", "/api/community/gaps/demand")

    with st.form("create_post"):
        title = st.text_input("Title (6–200)")
        body = st.text_area("Body (20–6000)", height=120)
        submitted = st.form_submit_button("POST /api/community/posts")
    if submitted:
        request(
            "POST",
            "/api/community/posts",
            json_body={"title": title, "body": body},
        )

    post_id = st.text_input("Post id")
    c4, c5 = st.columns(2)
    with c4:
        if st.button("Get post", use_container_width=True) and post_id.strip():
            request("GET", f"/api/community/posts/{post_id.strip()}")
    with c5:
        if st.button("Recruit agents", use_container_width=True) and post_id.strip():
            request("POST", f"/api/community/posts/{post_id.strip()}/recruit")

    comment_id = st.text_input("Comment id (publish)")
    if st.button("Publish comment") and comment_id.strip():
        request("POST", f"/api/community/comments/{comment_id.strip()}/publish")


def page_social() -> None:
    st.subheader("Social")
    tab_feed, tab_connections = st.tabs(["Feed", "Connections"])

    with tab_feed:
        c1, c2 = st.columns(2)
        with c1:
            if st.button("GET /api/social/feed", use_container_width=True):
                request("GET", "/api/social/feed")
        with c2:
            if st.button("POST /api/social/feed/agent", use_container_width=True):
                request("POST", "/api/social/feed/agent")

        with st.form("create_feed_post"):
            body = st.text_area("Post body (1–4000)", height=100)
            presentation = st.selectbox("Presentation", ["post", "story"])
            location = st.text_input("Location (optional)")
            submitted = st.form_submit_button("POST /api/social/feed")
        if submitted:
            payload: dict[str, Any] = {"body": body, "presentation": presentation}
            if location.strip():
                payload["location"] = location.strip()
            request("POST", "/api/social/feed", json_body=payload)

        with st.form("draft_feed"):
            notes = st.text_area("Draft notes (3–2000)", height=80)
            draft_submitted = st.form_submit_button("POST /api/social/feed/draft")
        if draft_submitted:
            request("POST", "/api/social/feed/draft", json_body={"notes": notes})

        post_id = st.text_input("Post id to react", key="react_post_id")
        reaction = st.selectbox("Reaction", ["like", "insightful", "same", "clear"])
        if st.button("POST /api/social/feed/{id}/react") and post_id.strip():
            value = None if reaction == "clear" else reaction
            request(
                "POST",
                f"/api/social/feed/{post_id.strip()}/react",
                json_body={"reaction": value},
            )

    with tab_connections:
        if st.button("GET /api/social/connections", use_container_width=True):
            request("GET", "/api/social/connections")

        other_id = st.text_input("Other user id", key="social_other_id")
        c1, c2, c3 = st.columns(3)
        with c1:
            if st.button("Status", use_container_width=True) and other_id.strip():
                request("GET", f"/api/social/connections/{other_id.strip()}")
        with c2:
            if st.button("Accept", use_container_width=True) and other_id.strip():
                request(
                    "POST",
                    f"/api/social/connections/{other_id.strip()}/respond",
                    json_body={"accept": True},
                )
        with c3:
            if st.button("Decline", use_container_width=True) and other_id.strip():
                request(
                    "POST",
                    f"/api/social/connections/{other_id.strip()}/respond",
                    json_body={"accept": False},
                )

        with st.form("request_connection"):
            recipient_id = st.text_input("Recipient user id")
            note = st.text_input("Note (optional)")
            source = st.selectbox(
                "Source",
                ["direct", "discovery", "interview", "community", "feed"],
            )
            submitted = st.form_submit_button("POST /api/social/connections")
        if submitted:
            body = {"recipient_id": recipient_id.strip(), "source": source}
            if note.strip():
                body["note"] = note.strip()
            request("POST", "/api/social/connections", json_body=body)

        if st.button("Withdraw pending") and other_id.strip():
            request("POST", f"/api/social/connections/{other_id.strip()}/withdraw")


def page_messages() -> None:
    st.subheader("Messages")
    if st.button("GET /api/messages"):
        request("GET", "/api/messages")

    other_id = st.text_input("Other user id")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Load thread", use_container_width=True) and other_id.strip():
            request("GET", f"/api/messages/{other_id.strip()}")
    with c2:
        if st.button("Mark read", use_container_width=True) and other_id.strip():
            request("POST", f"/api/messages/{other_id.strip()}/read")

    with st.form("send_message"):
        body = st.text_area("Message body (1–2000)")
        submitted = st.form_submit_button("Send")
    if submitted:
        if not other_id.strip():
            st.warning("Enter other user id")
        else:
            request(
                "POST",
                f"/api/messages/{other_id.strip()}",
                json_body={"body": body},
            )


def page_raw() -> None:
    st.subheader("Raw request")
    method = st.selectbox("Method", ["GET", "POST", "PATCH", "DELETE", "PUT"])
    path = st.text_input("Path", value="/health")
    params_raw = st.text_area("Query params (JSON object)", value="{}")
    body_raw = st.text_area("JSON body (optional)", value="")
    if st.button("Send"):
        try:
            params = json.loads(params_raw) if params_raw.strip() else None
        except json.JSONDecodeError:
            st.error("Query params must be valid JSON")
            return
        json_body = None
        if body_raw.strip():
            try:
                json_body = json.loads(body_raw)
            except json.JSONDecodeError:
                st.error("Body must be valid JSON")
                return
        request(method, path, params=params, json_body=json_body)


def main() -> None:
    st.set_page_config(page_title="AgentCircle API Tester", layout="wide")
    init_state()
    sidebar()

    st.title("AgentCircle API Tester")
    st.caption("Lightweight Streamlit harness for the FastAPI backend.")

    pages = {
        "Health": page_health,
        "Auth": page_auth,
        "Profile": page_profile,
        "Persona": page_persona,
        "Discover": page_discover,
        "Community": page_community,
        "Social": page_social,
        "Messages": page_messages,
        "Raw": page_raw,
    }
    choice = st.radio("Surface", list(pages), horizontal=True)
    st.divider()
    pages[choice]()

    if st.session_state.last_response:
        with st.expander("Last response meta", expanded=False):
            meta = {
                k: v
                for k, v in st.session_state.last_response.items()
                if k != "body"
            }
            st.json(meta)


if __name__ == "__main__":
    main()
