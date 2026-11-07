from __future__ import annotations

import logging
import os

import streamlit as st
from dotenv import load_dotenv
from google.api_core.exceptions import (
    FailedPrecondition,
    GoogleAPICallError,
    NotFound,
    PermissionDenied,
)

from firebase_client import get_firestore_client
from gemini_provider import GeminiProvider
from models import Principal
from rag_service import answer_question


logger = logging.getLogger(__name__)
load_dotenv()

st.set_page_config(
    page_title="Milti-tenant RAG | httpsumita",
    page_icon="🔐",
    layout="wide",
    initial_sidebar_state="expanded",
)


def gemini_api_key() -> str | None:
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if api_key:
        return api_key
    try:
        return st.secrets.get("GEMINI_API_KEY") or st.secrets.get("GOOGLE_API_KEY")
    except (FileNotFoundError, KeyError):
        return None


def render_chat(principal: Principal, project_id: str) -> None:
    st.subheader(f"Chat · {principal.tenant_id}")
    api_key = gemini_api_key()
    if not api_key:
        st.warning("Configure GEMINI_API_KEY to enable chat.")
        return

    history_key = f"chat:{principal.user_id}:{principal.tenant_id}"
    messages = st.session_state.setdefault(history_key, [])
    for message in messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    question = st.chat_input("Ask about your tenant's documents")
    if not question:
        return

    messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        with st.spinner("Searching authorized documents..."):
            try:
                db = get_firestore_client(project_id)
                response = answer_question(
                    db,
                    principal,
                    question,
                    GeminiProvider(api_key),
                )
            except FailedPrecondition:
                logger.warning("Firestore rejected the vector query; check the composite vector index.", exc_info=True)
                response = (
                    "Firestore needs the tenant-filtered vector index before it can search. "
                    "Deploy `firestore.indexes.json` and wait for the index to finish building."
                )
            except NotFound:
                logger.warning("Firestore database or query target was not found.", exc_info=True)
                response = "The Firestore database or chunks collection is unavailable for this project."
            except PermissionDenied:
                logger.warning("Firestore denied the tenant-scoped vector query.", exc_info=True)
                response = "Firestore denied access to the tenant's chunks. Check the ADC account's project permissions."
            except GoogleAPICallError:
                logger.exception("Firestore tenant-scoped vector query failed")
                response = "Firestore search failed. Check database availability and permissions."
            except Exception:
                logger.exception("Tenant-scoped chat request failed")
                response = "I couldn't complete that request. Check the Gemini configuration and try again."
        st.markdown(response)
    messages.append({"role": "assistant", "content": response})


def firebase_project_id() -> str | None:
    project_id = os.getenv("FIREBASE_PROJECT_ID")
    if project_id:
        return project_id
    try:
        return st.secrets.get("FIREBASE_PROJECT_ID")
    except (FileNotFoundError, KeyError):
        return None


PUBLIC_DEMO_PRINCIPAL = Principal(
    user_id="public-demo-visitor",
    tenant_id="tenant-a",
    roles=frozenset({"employee"}),
)


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
    .recruiter-panel { border-left: 3px solid #70d6c3; padding: .2rem 0 .2rem 1.15rem; }
    .recruiter-panel h3 { margin: .15rem 0 .45rem; font-size: 1.08rem; }
    .question-example { padding: .6rem 0; border-top: 1px solid rgba(148,163,184,.16); color: #d7e2ef; }
    .panel-note { margin-top: .8rem; color: #9eacbd; font-size: .88rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.markdown("## Multi-Tenant Aware RAG")
    st.markdown("[by @httpsumita](https://github.com/httpsumita)")
    st.divider()
    st.markdown("Public demo · Tenant A · employee access")
    project_id = firebase_project_id()
    st.markdown("🟢 Ask away - Get info about me")
    st.markdown("🟢 Check if you getting the right data.")
    if st.button("Open Tenant A chat", use_container_width=True):
        st.session_state["public_demo_open"] = True
        st.rerun()
    if st.session_state.get("public_demo_open") and st.button(
        "Back to overview", use_container_width=True
    ):
        st.session_state["public_demo_open"] = False
        st.rerun()
    st.divider()
    st.caption("Anyone can use the public Tenant A demo.")

if st.session_state.get("public_demo_open"):
    if project_id:
        render_chat(PUBLIC_DEMO_PRINCIPAL, project_id)
    else:
        st.error("Configure FIREBASE_PROJECT_ID before enabling the public demo.")
    st.stop()
else:
    st.markdown(
        """
        <section class="hero">
            <div class="eyebrow">Public demo · Tenant A</div>
            <h1>Candidate knowledge, with access built in.</h1>
            <p>Ask about the public demo profile's experience, skills, projects, and outcomes. No account is needed.</p>
        </section>
        """,
        unsafe_allow_html=True,
    )

    st.write("")

    status_col, boundary_col, audit_col = st.columns(3)
    with status_col:
        st.markdown(
            '<div class="card"><h3>🏢 Tenant A workspace</h3><div class="muted">This public demo uses a fixed employee role and can search only Tenant A.</div></div>',
            unsafe_allow_html=True,
        )
    with boundary_col:
        st.markdown(
            '<div class="card"><h3>🧑‍💼 Candidate profile</h3><div class="muted">Professional experience and skills are in Tenant A; education details are stored separately.</div></div>',
            unsafe_allow_html=True,
        )
    with audit_col:
        st.markdown(
            '<div class="card"><h3>🔒 Tenant boundary</h3><div class="muted">Education details belong to Tenant B and are excluded from this Tenant A demo.</div></div>',
            unsafe_allow_html=True,
        )

    st.subheader("Recruiter question starters")
    questions_left, questions_right = st.columns(2)
    with questions_left:
        st.markdown(
            """
            <div class="step"><span class="step-no">01</span><div><b>Experience</b><div class="muted">What recruiting or assessment workflows has this candidate automated?</div></div></div>
            <div class="step"><span class="step-no">02</span><div><b>Technical skills</b><div class="muted">Which AI, LLM, and application technologies appear in the profile?</div></div></div>
            """,
            unsafe_allow_html=True,
        )
    with questions_right:
        st.markdown(
            """
            <div class="step"><span class="step-no">03</span><div><b>Projects</b><div class="muted">Which projects use retrieval-augmented generation or speech AI?</div></div></div>
            <div class="step"><span class="step-no">04</span><div><b>Outcomes</b><div class="muted">What measurable results are reported for the candidate's work?</div></div></div>
            """,
            unsafe_allow_html=True,
        )

    st.warning(
        "This app is public: anyone can query employee-accessible Tenant A content and use "
        "the app owner's Gemini quota. Do not store sensitive or private data in Tenant A, "
        "and do not enter personal information in chat. Select **Open Tenant A chat** to continue."
    )
