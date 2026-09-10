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

st.set_page_config(page_title="EchoTrace", layout="wide")


# ---------------------------------------------------------------------------
# Styling — light, minimal, one confident accent color. Inter throughout,
# no emoji, no decorative motifs — the content is the product.
# IMPORTANT: keep this string free of blank lines. Streamlit's
# unsafe_allow_html markdown still runs content through its markdown
# parser first, and a blank line inside gets read as a paragraph break,
# splitting the <style> tag apart so the raw CSS leaks onto the page.
# ---------------------------------------------------------------------------

st.markdown(
    """
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
    .stApp { background-color: #F7F8FA; }
    [data-testid="stSidebar"] { background-color: #FFFFFF; border-right: 1px solid #E4E7EC; }
    [data-testid="stHeader"] { background-color: transparent; }
    h1, h2, h3 { font-family: 'Inter', sans-serif; font-weight: 700; color: #1A1D23; }
    .stCaption, [data-testid="stCaptionContainer"] { color: #6B7280 !important; }
    p, span, label, div { color: #1A1D23; }
    .stTabs [data-baseweb="tab-list"] { gap: 4px; border-bottom: 1px solid #E4E7EC; }
    .stTabs [data-baseweb="tab"] { color: #6B7280; font-weight: 500; }
    .stTabs [aria-selected="true"] { color: #4338CA !important; border-bottom: 2px solid #4338CA !important; }
    .stTextInput input, .stSelectbox div[data-baseweb="select"] > div {
        background-color: #FFFFFF;
        color: #1A1D23;
        border: 1px solid #D0D5DD;
        border-radius: 6px;
    }
    .stTextInput input:focus { border-color: #4338CA; }
    button[data-testid^="stBaseButton"] {
        background-color: #FFFFFF;
        color: #1A1D23;
        border: 1px solid #D0D5DD;
        border-radius: 6px;
        font-weight: 500;
    }
    button[data-testid^="stBaseButton"]:hover { border-color: #4338CA; color: #4338CA; }
    button[data-testid="stBaseButton-primary"], button[data-testid="stBaseButton-primaryFormSubmit"] {
        background-color: #4338CA;
        border: none;
        color: #FFFFFF;
        font-weight: 600;
    }
    button[data-testid="stBaseButton-primary"]:hover,
    button[data-testid="stBaseButton-primaryFormSubmit"]:hover { background-color: #3730A3; color: #FFFFFF; }
    [data-testid="stMetricValue"] { color: #1A1D23; font-weight: 700; }
    [data-testid="stMetricLabel"] { color: #6B7280; }
    .et-card {
        background: #FFFFFF;
        color: #1A1D23;
        border: 1px solid #E4E7EC;
        border-radius: 8px;
        padding: 14px 16px;
        margin-bottom: 8px;
        box-shadow: 0 1px 2px rgba(16,24,40,0.04);
    }
    .et-card .card-title { font-weight: 600; margin-bottom: 3px; }
    .et-card .card-meta { font-size: 0.82rem; color: #6B7280; }
    .et-badge {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        border-radius: 999px;
        padding: 6px 16px;
        font-weight: 600;
        font-size: 0.95rem;
        margin-bottom: 16px;
    }
    .et-badge-clear { background: #DCFCE7; color: #15803D; }
    .et-badge-flag { background: #FEE2E2; color: #B91C1C; }
    .et-badge-pending { background: #F3F4F6; color: #4B5563; }
    .et-wordmark { font-size: 1.6rem; font-weight: 700; color: #1A1D23; margin-bottom: 2px; }
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
    return requests.get(f"{API_BASE}{path}", headers=api_headers(), params=params, timeout=30)


def api_post(path: str, json: dict):
    return requests.post(f"{API_BASE}{path}", headers=api_headers(), json=json, timeout=60)


def short_label(article_id: str) -> str:
    """'7_288600912-garden-city-telegram-Mar-21-1974-p-1.jpg' -> 'Garden City Telegram'"""
    name_part = article_id.split("_", 1)[-1] if "_" in article_id else article_id
    name_part = re.sub(r"\.(jpg|jpeg|png)$", "", name_part, flags=re.IGNORECASE)
    words = [w for w in name_part.split("-") if w and not re.search(r"\d", w) and w.lower() != "p"]
    return " ".join(words[:4]).title() or article_id


# ---------------------------------------------------------------------------
# Auth page — small, centered box, not full width.
# ---------------------------------------------------------------------------


def login_register_page():
    left, mid, right = st.columns([1, 1.1, 1])
    with mid:
        st.markdown('<div class="et-wordmark">EchoTrace</div>', unsafe_allow_html=True)
        st.caption("Agentic cross-duplicate detection of AI-reworded news content")
        st.write("")

        login_tab, register_tab = st.tabs(["Log in", "Create account"])

        with login_tab:
            with st.form("login_form"):
                username = st.text_input("Username", key="login_username")
                password = st.text_input("Password", type="password", key="login_password")
                submitted = st.form_submit_button("Log in", use_container_width=True, type="primary")
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
                submitted = st.form_submit_button("Create account", use_container_width=True, type="primary")
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
# Case Files tab — near-duplicate retrieval + aggregation demo.
# ---------------------------------------------------------------------------


def render_verdict(result: dict):
    if not result.get("model_available"):
        st.markdown('<span class="et-badge et-badge-pending">Evidence pending</span>', unsafe_allow_html=True)
        st.info(result.get("message", "Detector checkpoint not yet loaded."))
        return

    agg = result.get("aggregated_score", 0.0)
    single = result.get("single_instance_score", 0.0)
    flagged = agg >= 0.5
    css_class = "et-badge-flag" if flagged else "et-badge-clear"
    label = "AI-reworded copy" if flagged else "Independent reporting"
    st.markdown(f'<span class="et-badge {css_class}">{label}</span>', unsafe_allow_html=True)

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
    fig.add_bar(name="Similarity to target", x=ids, y=similarities, marker_color="#4338CA")
    if model_available:
        fig.add_bar(name="AI-text score", x=ids, y=scores, marker_color="#B91C1C")
    fig.update_layout(
        barmode="group",
        height=360,
        margin=dict(l=10, r=10, t=30, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font_color="#1A1D23",
        font_family="Inter, sans-serif",
        legend=dict(orientation="h", y=1.1),
        yaxis_title="%",
        yaxis=dict(gridcolor="#E4E7EC"),
    )
    st.plotly_chart(fig, use_container_width=True)

    for e in evidence:
        score_text = f"{e['score'] * 100:.0f}%" if (model_available and e.get("score") is not None) else "pending"
        st.markdown(
            f"""<div class="et-card">
                <div class="card-title">{short_label(e['id'])}</div>
                <div class="card-meta">similarity {e['similarity']*100:.0f}% · AI-text score {score_text}</div>
            </div>""",
            unsafe_allow_html=True,
        )


def case_files_tab():
    resp = api_get("/api/articles/sample", limit=12)
    if resp.status_code == 401:
        st.session_state.clear()
        st.rerun()
    if resp.status_code != 200:
        st.error(f"Could not load sample articles ({resp.status_code}).")
        return

    st.caption(
        "Real historical newspaper articles (all genuinely human-written — this corpus "
        "predates AI text generation). Good for demonstrating retrieval and aggregation; "
        "see the Detector Test tab to see the detector flag real AI-generated text."
    )

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

        st.session_state["last_result"] = result_resp.json()
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


# ---------------------------------------------------------------------------
# Detector Test tab — real M-DAIGT examples (real human AND real machine
# labels), so the detector can be shown catching AI text, not just
# correctly clearing human text.
# ---------------------------------------------------------------------------


def detector_test_tab():
    # Samples are fetched once per session and cached — the API returns a
    # fresh ORDER BY RANDOM() batch on every call, so re-fetching on each
    # rerun (e.g. the rerun triggered by clicking "Run detector") would
    # silently swap the option list out from under the user's selection,
    # and the detector would end up scoring a different sample than the
    # one they picked. Only "Get new samples" is allowed to refresh it.
    if "mdaigt_samples" not in st.session_state:
        resp = api_get("/api/mdaigt/sample", limit=15, split="test")
        if resp.status_code == 401:
            st.session_state.clear()
            st.rerun()
        if resp.status_code != 200:
            st.error(f"Could not load M-DAIGT samples ({resp.status_code}).")
            return
        st.session_state["mdaigt_samples"] = resp.json()

    samples = st.session_state["mdaigt_samples"]
    id_to_sample = {s["id"]: s for s in samples}

    st.caption(
        "Real M-DAIGT test-set samples — a mix of genuine human-written and genuine "
        "AI-generated news text, held out during training. The label is only revealed "
        "after the detector runs, so this is a fair, blind check."
    )

    if st.button("Get new samples", key="mdaigt_refresh"):
        del st.session_state["mdaigt_samples"]
        st.session_state.pop("mdaigt_result", None)
        st.session_state.pop("mdaigt_sample_id", None)
        st.rerun()

    sample_id = st.selectbox(
        "Pick a sample",
        options=list(id_to_sample.keys()),
        format_func=lambda sid: f"{id_to_sample[sid]['preview'][:80]}…",
        key="mdaigt_choice",
    )

    if st.button("Run detector", type="primary", key="run_detector"):
        article_resp = api_get(f"/api/articles/{sample_id}")
        if article_resp.status_code != 200:
            st.error("Could not load sample.")
            return
        article = article_resp.json()

        with st.spinner("Scoring…"):
            result_resp = api_post("/api/detect", {"text": article["text"]})
        if result_resp.status_code == 401:
            st.session_state.clear()
            st.rerun()
        if result_resp.status_code != 200:
            st.error(f"Detection failed ({result_resp.status_code}).")
            return

        st.session_state["mdaigt_result"] = result_resp.json()
        st.session_state["mdaigt_sample_id"] = sample_id

    if "mdaigt_result" in st.session_state and st.session_state.get("mdaigt_sample_id") == sample_id:
        st.divider()
        result = st.session_state["mdaigt_result"]
        if not result.get("model_available"):
            st.markdown('<span class="et-badge et-badge-pending">Model not loaded</span>', unsafe_allow_html=True)
            st.info(result.get("message", ""))
            return

        predicted_score = result["score"]
        predicted_label = "machine" if predicted_score >= 0.5 else "human"
        true_label = id_to_sample[sample_id]["label"]
        correct = predicted_label == true_label

        col1, col2, col3 = st.columns(3)
        col1.metric("Predicted AI-text score", f"{predicted_score * 100:.1f}%")
        col2.metric("Predicted label", predicted_label.title())
        col3.metric("Real ground-truth label", true_label.title())

        if correct:
            st.markdown('<span class="et-badge et-badge-clear">Correct</span>', unsafe_allow_html=True)
        else:
            st.markdown('<span class="et-badge et-badge-flag">Incorrect</span>', unsafe_allow_html=True)


def investigate_page():
    st.markdown("## Case File")
    st.caption(f"Signed in as {st.session_state['username']}")

    tab1, tab2 = st.tabs(["Case Files", "Detector Test"])
    with tab1:
        case_files_tab()
    with tab2:
        detector_test_tab()


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
