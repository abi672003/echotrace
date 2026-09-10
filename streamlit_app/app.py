"""EchoTrace — production Streamlit client.

A real, authenticated web app: a login/register page gates access, then a
case-investigation page talks to the real FastAPI backend (retrieval,
detection, aggregation) over HTTP, carrying a JWT session token on every
request. No mock data, no bypassed auth — every request that reaches the
backend's protected endpoints is checked server-side.
"""

import re

import plotly.graph_objects as go
import requests
import streamlit as st

API_BASE = "http://localhost:8010"

st.set_page_config(page_title="EchoTrace", page_icon="🔎", layout="wide")


# ---------------------------------------------------------------------------
# Styling — a distinct "newsroom verification" identity: deep ink-navy
# dominant, a warm copper accent (an ink-stamp feel, not neon), an editorial
# serif for headings paired with a clean sans for body/UI text. Built to
# work with Streamlit's own component structure rather than fight it.
# ---------------------------------------------------------------------------

st.markdown(
    """
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Newsreader:ital,opsz,wght@0,6..72,500;0,6..72,700;1,6..72,500&family=IBM+Plex+Sans:wght@400;500;600&display=swap" rel="stylesheet">
    <style>
    html, body, [class*="css"] { font-family: 'IBM Plex Sans', sans-serif; }
    .stApp { background-color: #0F1B2D; }
    [data-testid="stSidebar"] { background-color: #0A1220; border-right: 1px solid #213655; }
    [data-testid="stHeader"] { background-color: transparent; }
    h1, h2, h3 {
        font-family: 'Newsreader', serif;
        font-weight: 600;
        color: #E9E4D8;
        letter-spacing: 0.01em;
    }
    .stCaption, [data-testid="stCaptionContainer"] { color: #8C97AC !important; }
    p, span, label, div { color: #E9E4D8; }
    .stTabs [data-baseweb="tab-list"] { gap: 4px; border-bottom: 1px solid #213655; }
    .stTabs [data-baseweb="tab"] {
        color: #8C97AC;
        font-weight: 500;
    }
    .stTabs [aria-selected="true"] {
        color: #E0974F !important;
        border-bottom: 2px solid #C67C3E !important;
    }
    .stTextInput input, .stSelectbox div[data-baseweb="select"] > div {
        background-color: #16243A;
        color: #E9E4D8;
        border: 1px solid #213655;
        border-radius: 4px;
    }
    .stTextInput input:focus { border-color: #C67C3E; }
    .stButton > button {
        background-color: #16243A;
        color: #E9E4D8;
        border: 1px solid #213655;
        border-radius: 4px;
        font-weight: 500;
    }
    .stButton > button:hover { border-color: #C67C3E; color: #E0974F; }
    .stButton > button[kind="primary"], .stFormSubmitButton > button[kind="primary"] {
        background-color: #C67C3E;
        border: none;
        color: #0A1220;
        font-weight: 600;
    }
    .stButton > button[kind="primary"]:hover,
    .stFormSubmitButton > button[kind="primary"]:hover { background-color: #E0974F; color: #0A1220; }
    [data-testid="stMetricValue"] { color: #E0974F; font-family: 'Newsreader', serif; }
    [data-testid="stMetricLabel"] { color: #8C97AC; }
    .echotrace-card {
        background: #16243A;
        color: #E9E4D8;
        border: 1px solid #213655;
        border-left: 3px solid #C67C3E;
        border-radius: 3px;
        padding: 14px 16px;
        margin-bottom: 8px;
    }
    .echotrace-card .card-title { font-weight: 600; margin-bottom: 3px; }
    .echotrace-card .card-meta { font-size: 0.8rem; color: #8C97AC; }
    .verdict-stamp {
        display: inline-block;
        border: 3px solid;
        border-radius: 4px;
        padding: 10px 26px;
        font-family: 'Newsreader', serif;
        font-weight: 700;
        font-style: italic;
        font-size: 1.3rem;
        letter-spacing: 0.04em;
        transform: rotate(-1.5deg);
        margin-bottom: 18px;
    }
    .verdict-clear { border-color: #4C9A83; color: #4C9A83; }
    .verdict-flag { border-color: #C1503C; color: #C1503C; }
    .verdict-pending { border-color: #7A8699; color: #7A8699; }
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# API client — every call carries the session's bearer token once logged in.
# ---------------------------------------------------------------------------


def api_headers() -> dict:
    token = st.session_state.get("token")
    return {"Authorization": f"Bearer {token}"} if token else {}


def api_get(path: str, **params):
    resp = requests.get(f"{API_BASE}{path}", headers=api_headers(), params=params, timeout=30)
    return resp


def api_post(path: str, json: dict):
    resp = requests.post(f"{API_BASE}{path}", headers=api_headers(), json=json, timeout=60)
    return resp


def short_label(article_id: str) -> str:
    """'7_288600912-garden-city-telegram-Mar-21-1974-p-1.jpg' -> 'Garden City Telegram'"""
    name_part = article_id.split("_", 1)[-1] if "_" in article_id else article_id
    name_part = re.sub(r"\.(jpg|jpeg|png)$", "", name_part, flags=re.IGNORECASE)
    words = [w for w in name_part.split("-") if w and not re.search(r"\d", w) and w.lower() != "p"]
    return " ".join(words[:4]).title() or article_id


# ---------------------------------------------------------------------------
# Auth pages
# ---------------------------------------------------------------------------


def login_register_page():
    st.markdown("# 🔎 EchoTrace")
    st.caption("Agentic cross-duplicate detection of AI-reworded news content")
    st.write("")

    login_tab, register_tab = st.tabs(["Log in", "Create account"])

    with login_tab:
        with st.form("login_form"):
            username = st.text_input("Username", key="login_username")
            password = st.text_input("Password", type="password", key="login_password")
            submitted = st.form_submit_button("Log in", use_container_width=True)
        if submitted:
            resp = api_post("/api/auth/login", {"username": username, "password": password})
            if resp.status_code == 200:
                data = resp.json()
                st.session_state["token"] = data["access_token"]
                st.session_state["username"] = data["username"]
                st.rerun()
            else:
                st.error(resp.json().get("detail", "Login failed."))

    with register_tab:
        with st.form("register_form"):
            new_username = st.text_input("Choose a username", key="reg_username")
            new_password = st.text_input(
                "Choose a password", type="password", key="reg_password",
                help="At least 8 characters.",
            )
            confirm_password = st.text_input("Confirm password", type="password", key="reg_confirm")
            submitted = st.form_submit_button("Create account", use_container_width=True)
        if submitted:
            if new_password != confirm_password:
                st.error("Passwords don't match.")
            else:
                resp = api_post("/api/auth/register", {"username": new_username, "password": new_password})
                if resp.status_code == 200:
                    data = resp.json()
                    st.session_state["token"] = data["access_token"]
                    st.session_state["username"] = data["username"]
                    st.rerun()
                else:
                    st.error(resp.json().get("detail", "Registration failed."))


# ---------------------------------------------------------------------------
# Main app (post-login)
# ---------------------------------------------------------------------------


def render_verdict(result: dict):
    if not result.get("model_available"):
        st.markdown(
            '<div class="verdict-stamp verdict-pending">EVIDENCE PENDING</div>',
            unsafe_allow_html=True,
        )
        st.info(result.get("message", "Detector checkpoint not yet loaded."))
        return

    agg = result.get("aggregated_score", 0.0)
    single = result.get("single_instance_score", 0.0)
    flagged = agg >= 0.5
    css_class = "verdict-flag" if flagged else "verdict-clear"
    label = "AI-REWORDED COPY" if flagged else "INDEPENDENT REPORTING"
    st.markdown(f'<div class="verdict-stamp {css_class}">{label}</div>', unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    col1.metric("Aggregated score", f"{agg * 100:.1f}%", delta=f"{(agg - single) * 100:+.1f}% vs. single-instance")
    col2.metric("Single-instance score", f"{single * 100:.1f}%")


def render_evidence(evidence: list[dict], model_available: bool):
    if not evidence:
        st.write("No near-duplicate copies found.")
        return

    st.subheader("Evidence trail")
    ids = [short_label(e["id"]) for e in evidence]
    similarities = [e["similarity"] * 100 for e in evidence]
    scores = [e["score"] * 100 if e.get("score") is not None else 0 for e in evidence]

    fig = go.Figure()
    fig.add_bar(name="Similarity to target", x=ids, y=similarities, marker_color="#5B7FA6")
    if model_available:
        fig.add_bar(name="AI-text score", x=ids, y=scores, marker_color="#C1503C")
    fig.update_layout(
        barmode="group",
        height=360,
        margin=dict(l=10, r=10, t=30, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font_color="#E9E4D8",
        font_family="IBM Plex Sans, sans-serif",
        legend=dict(orientation="h", y=1.1),
        yaxis_title="%",
        yaxis=dict(gridcolor="#213655"),
    )
    st.plotly_chart(fig, use_container_width=True)

    for e in evidence:
        score_text = f"{e['score'] * 100:.0f}%" if (model_available and e.get("score") is not None) else "pending"
        st.markdown(
            f"""<div class="echotrace-card">
                <div class="card-title">{short_label(e['id'])}</div>
                <div class="card-meta">similarity {e['similarity']*100:.0f}% · AI-text score {score_text}</div>
            </div>""",
            unsafe_allow_html=True,
        )


def investigate_page():
    st.markdown(f"# 🔎 EchoTrace — Case File")
    st.caption(f"Logged in as **{st.session_state['username']}**")

    resp = api_get("/api/articles/sample", limit=12)
    if resp.status_code == 401:
        st.session_state.clear()
        st.rerun()
    if resp.status_code != 200:
        st.error(f"Could not load sample articles ({resp.status_code}).")
        return

    samples = resp.json()
    options = {f"{s['preview'][:80]}…": s["id"] for s in samples}
    choice = st.selectbox("Open a case file", options.keys())
    article_id = options[choice]

    if st.button("Investigate", type="primary"):
        article_resp = api_get(f"/api/articles/{article_id}")
        if article_resp.status_code != 200:
            st.error("Could not load article.")
            return
        article = article_resp.json()

        with st.spinner("Retrieving near-duplicate evidence…"):
            result_resp = api_post(
                "/api/investigate", {"text": article["text"], "article_id": article_id, "k": 6}
            )
        if result_resp.status_code == 401:
            st.session_state.clear()
            st.rerun()
        if result_resp.status_code != 200:
            st.error(f"Investigation failed ({result_resp.status_code}).")
            return

        result = result_resp.json()
        st.session_state["last_result"] = result
        st.session_state["last_article"] = article

    if "last_result" in st.session_state:
        st.divider()
        with st.expander("Target article text", expanded=False):
            st.write(st.session_state["last_article"]["text"][:1500])
        render_verdict(st.session_state["last_result"])
        render_evidence(
            st.session_state["last_result"].get("evidence", []),
            st.session_state["last_result"].get("model_available", False),
        )


def main():
    if "token" not in st.session_state:
        login_register_page()
        return

    with st.sidebar:
        st.markdown(f"**{st.session_state['username']}**")
        if st.button("Log out"):
            st.session_state.clear()
            st.rerun()

    investigate_page()


if __name__ == "__main__":
    main()
