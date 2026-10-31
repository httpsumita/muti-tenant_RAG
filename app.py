from __future__ import annotations

import logging
import os

import streamlit as st

from firebase_client import get_firestore_client


logger = logging.getLogger(__name__)

st.set_page_config(
    page_title="Tenant-aware RAG | Atlas",
    page_icon="🔐",
    layout="wide",
    initial_sidebar_state="expanded",
)


# The Streamlit UI does not yet authenticate users or invoke retrieval.
# Do not present user-controlled tenant/role values as authenticated identity.
def gemini_key_configured() -> bool:
    key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if key:
        return True
    try:
        return bool(st.secrets.get("GEMINI_API_KEY") or st.secrets.get("GOOGLE_API_KEY"))
    except (FileNotFoundError, KeyError):
        return False


def firebase_project_id() -> str | None:
    project_id = os.getenv("FIREBASE_PROJECT_ID")
    if project_id:
        return project_id
    try:
        return st.secrets.get("FIREBASE_PROJECT_ID")
    except (FileNotFoundError, KeyError):
        return None


st.markdown(
    """
    <style>
      :root { color-scheme: dark; }
      .block-container { max-width: 1180px; padding-top: 2.2rem; padding-bottom: 4rem; }
      .hero { padding: 2rem 2.2rem; border: 1px solid rgba(148,163,184,.2);
              border-radius: 22px; background: linear-gradient(120deg,#101827,#14253a 65%,#18304a); }
      .eyebrow { color: #70d6c3; font-size: .78rem; font-weight: 700; letter-spacing: .14em; text-transform: uppercase; }
      .hero h1 { font-size: clamp(2rem,4vw,3.2rem); margin: .55rem 0 .7rem; }
      .hero p { color: #b7c5d6; font-size: 1.05rem; max-width: 760px; }
      .card { padding: 1.15rem 1.25rem; min-height: 145px; border: 1px solid rgba(148,163,184,.2);
              border-radius: 16px; background: rgba(15,23,42,.58); }
      .card h3 { margin: .2rem 0 .6rem; font-size: 1.05rem; }
      .muted { color: #a7b5c7; font-size: .92rem; }
      .step { display: flex; gap: .85rem; align-items: flex-start; margin: .9rem 0; }
      .step-no { color: #70d6c3; font-weight: 800; min-width: 1.7rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.markdown("## 🔐 Atlas RAG")
    st.caption("Permission-aware knowledge assistant")
    st.divider()
    st.markdown("**Build status**")
    st.markdown("🟡 Identity & authorization — next milestone")
    project_id = firebase_project_id()
    st.markdown("🟢 Firebase project — configured" if project_id else "⚪ Firebase project — not configured")
    st.markdown("🟢 Gemini key — " + ("configured" if gemini_key_configured() else "not configured"))
    if st.button("Initialize Firestore client", disabled=not project_id):
        try:
            get_firestore_client(project_id)
            st.session_state["firestore_client_initialized"] = True
        except Exception:
            logger.exception("Firestore client initialization failed")
            st.session_state["firestore_client_initialized"] = False
            st.error("Could not initialize Firestore. Check the project ID and ADC credentials.")
    if st.session_state.get("firestore_client_initialized"):
        st.caption("Admin client initialized; no documents accessed.")
    elif project_id:
        st.caption("ADC credentials will be used. No documents are accessed yet.")
    st.divider()
    st.caption("Local learning build · synthetic data only")

st.markdown(
    """
    <section class="hero">
      <div class="eyebrow">A safer way to ask company knowledge</div>
      <h1>Answers grounded in the right access.</h1>
      <p>Build a multi-tenant RAG assistant that checks identity and document permissions
      before any private content is sent to Gemini.</p>
    </section>
    """,
    unsafe_allow_html=True,
)

st.write("")

status_col, boundary_col, audit_col = st.columns(3)
with status_col:
    st.markdown(
        '<div class="card"><h3>🪪 Verified identity</h3><div class="muted">Authentication is not connected yet. Tenant identity will come from a trusted sign-in flow—not a form field.</div></div>',
        unsafe_allow_html=True,
    )
with boundary_col:
    st.markdown(
        '<div class="card"><h3>🛡️ Permission-first retrieval</h3><div class="muted">No document text is retrieved or sent to Gemini in this scaffold. Authorization must be enforced before generation.</div></div>',
        unsafe_allow_html=True,
    )
with audit_col:
    st.markdown(
        '<div class="card"><h3>🧾 Retrieval audit</h3><div class="muted">The next data milestone will record which authorized document chunks were returned for each request.</div></div>',
        unsafe_allow_html=True,
    )

st.subheader("Build roadmap")
roadmap_left, roadmap_right = st.columns(2)
with roadmap_left:
    st.markdown(
        """
        <div class="step"><span class="step-no">01</span><div><b>Identity and tenant context</b><div class="muted">Verify a user and derive their tenant and roles securely.</div></div></div>
        <div class="step"><span class="step-no">02</span><div><b>Firestore data model</b><div class="muted">Store tenant-scoped documents, chunks, ACLs, and audit events.</div></div></div>
        """,
        unsafe_allow_html=True,
    )
with roadmap_right:
    st.markdown(
        """
        <div class="step"><span class="step-no">03</span><div><b>Authorized retrieval</b><div class="muted">Filter by tenant and effective permissions before returning chunk text.</div></div></div>
        <div class="step"><span class="step-no">04</span><div><b>Gemini answers</b><div class="muted">Generate grounded responses using only the already-authorized context.</div></div></div>
        """,
        unsafe_allow_html=True,
    )

st.info(
    "Firestore client setup is available for local development, but this app has no user "
    "authentication or document operations yet. Chat and uploads stay disabled until "
    "verified identity and trusted tenant/role resolution are wired in. Do not deploy this "
    "Admin-SDK scaffold publicly or use it with private company data."
)
