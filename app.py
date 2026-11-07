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

from firebase_auth import (
    FirebaseAccountExistsError,
    FirebaseAuthError,
    InvalidFirebaseTokenError,
    authenticate_with_password,
    resolve_principal,
    resolve_principals,
    sign_in_with_password,
    sign_up_with_password,
    verify_identity_token,
)
from firebase_client import get_firestore_client
from gemini_provider import GeminiProvider
from models import Principal
from provision_tenant import (
    DEFAULT_SIGNUP_ROLE,
    DEFAULT_SIGNUP_TENANT_ID,
    TenantProvisioningError,
    provision_tenant_membership,
)
from rag_service import answer_question


logger = logging.getLogger(__name__)
load_dotenv()

st.set_page_config(
    page_title="Milti-tenant RAG | httpsumita",
    page_icon="🔐",
    layout="wide",
    initial_sidebar_state="expanded",
)


# Do not present user-controlled tenant/role values as authenticated identity.
def gemini_key_configured() -> bool:
    return bool(gemini_api_key())


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


def firebase_web_api_key() -> str | None:
    api_key = os.getenv("FIREBASE_WEB_API_KEY")
    if api_key:
        return api_key
    try:
        return st.secrets.get("FIREBASE_WEB_API_KEY")
    except (FileNotFoundError, KeyError):
        return None


def render_authentication(project_id: str | None, api_key: str | None) -> Principal | None:
    if not project_id or not api_key:
        st.warning("Configure FIREBASE_PROJECT_ID and FIREBASE_WEB_API_KEY to sign in.")
        return None

    pending_signup = st.session_state.get("tenant_signup_pending")
    if pending_signup:
        st.info("Your account is ready. Finish joining Tenant A to continue.")
        if st.button("Join Tenant A", key="finish-tenant-signup"):
            try:
                db = get_firestore_client(project_id)
                identity = verify_identity_token(pending_signup["id_token"], project_id)
                if identity.uid != pending_signup["uid"]:
                    raise FirebaseAuthError("The Firebase account identity did not match signup.")
                provision_tenant_membership(
                    db,
                    tenant_id=DEFAULT_SIGNUP_TENANT_ID,
                    firebase_uid=identity.uid,
                    roles=[DEFAULT_SIGNUP_ROLE],
                )
                st.session_state["firebase_id_token"] = pending_signup["id_token"]
                st.session_state.pop("tenant_signup_pending", None)
                st.rerun()
            except FirebaseAuthError as exc:
                st.error(str(exc))
            except GoogleAPICallError:
                st.error(
                    "Firestore could not finish tenant setup. Create the database and grant "
                    "the ADC account write access, then retry. No tenant access was granted."
                )
            except Exception:
                logger.exception("Tenant signup provisioning failed")
                st.error("Tenant setup failed. No access was granted; retry after fixing Firebase.")
        return None

    id_token = st.session_state.get("firebase_id_token")
    if id_token:
        try:
            db = get_firestore_client(project_id)
            principals = resolve_principals(id_token, project_id, db)
        except InvalidFirebaseTokenError:
            st.session_state.pop("firebase_id_token", None)
            st.info("Your sign-in expired. Please sign in again.")
            st.rerun()
        except FirebaseAuthError as exc:
            st.error(str(exc))
            if st.button("Sign out", key="membership-sign-out"):
                st.session_state.pop("firebase_id_token", None)
                st.rerun()
            return None
        except Exception:
            logger.exception("Firebase session verification failed")
            st.error("Could not verify your session. Check Firebase configuration and try again.")
            if st.button("Sign out", key="session-error-sign-out"):
                st.session_state.pop("firebase_id_token", None)
                st.rerun()
            return None

        principals_by_tenant = {principal.tenant_id: principal for principal in principals}
        selected_tenant = st.selectbox(
            "Tenant workspace",
            options=tuple(principals_by_tenant),
            key="active-tenant-selection",
        )
        principal = principals_by_tenant.get(selected_tenant)
        if principal is None:
            st.error("You do not have access to the selected tenant.")
            return None

        st.success("Signed in")
        st.caption(f"Tenant: {principal.tenant_id}")
        st.caption(f"Roles: {', '.join(sorted(principal.roles))}")
        if st.button("Sign out", key="authenticated-sign-out"):
            st.session_state.pop("firebase_id_token", None)
            st.rerun()
        return principal

    account_mode = st.radio(
        "Account",
        ("Sign in", "Join Tenant A"),
        horizontal=True,
        key="account-mode",
    )

    if account_mode == "Join Tenant A":
        with st.form("firebase-recruiter-sign-up"):
            email = st.text_input("Email", autocomplete="email")
            password = st.text_input("Password", type="password", autocomplete="new-password")
            st.caption(
                "New accounts automatically join Tenant A with employee access. HR-only "
                "documents require an authorized HR role."
            )
            submitted = st.form_submit_button("Create account and join", use_container_width=True)

        if submitted:
            try:
                db = get_firestore_client(project_id)
                next(db.collections(), None)
            except GoogleAPICallError:
                st.error(
                    "Firestore is not ready or the ADC account cannot access it. Create a "
                    "Firestore database and grant the ADC account write access. No Auth account was created."
                )
                return None
            except Exception:
                logger.exception("Firestore signup preflight failed")
                st.error("Could not check Firestore readiness. No Auth account was created.")
                return None

            try:
                id_token, uid = sign_up_with_password(email, password, api_key)
            except FirebaseAccountExistsError:
                try:
                    id_token = sign_in_with_password(email, password, api_key)
                    uid = verify_identity_token(id_token, project_id).uid
                except FirebaseAuthError as exc:
                    st.error(str(exc))
                    return None
            except FirebaseAuthError as exc:
                st.error(str(exc))
                return None
            except Exception:
                logger.exception("Firebase tenant account creation failed")
                st.error("Account creation failed. Check Firebase Authentication configuration.")
                return None

            st.session_state["tenant_signup_pending"] = {
                "id_token": id_token,
                "uid": uid,
            }

            try:
                identity = verify_identity_token(id_token, project_id)
                if identity.uid != uid:
                    raise FirebaseAuthError("Firebase returned mismatched account identity data.")
                provision_tenant_membership(
                    db,
                    tenant_id=DEFAULT_SIGNUP_TENANT_ID,
                    firebase_uid=uid,
                    roles=[DEFAULT_SIGNUP_ROLE],
                )
            except GoogleAPICallError:
                st.error(
                    "Your account was created, but Tenant A access could not be saved. "
                    "Fix Firestore access and choose Join Tenant A to retry."
                )
                return None
            except TenantProvisioningError as exc:
                st.error(str(exc))
                return None
            except FirebaseAuthError as exc:
                st.error(f"Your account was created, but tenant access could not be verified: {exc}")
                return None
            except Exception:
                logger.exception("Tenant A signup membership creation failed")
                st.error("Your account was created, but Tenant A access could not be saved. Retry setup.")
                return None

            st.session_state.pop("tenant_signup_pending", None)
            st.session_state["firebase_id_token"] = id_token
            st.rerun()
        return None

    with st.form("firebase-sign-in"):
        email = st.text_input("Email", autocomplete="email")
        password = st.text_input("Password", type="password", autocomplete="current-password")
        submitted = st.form_submit_button("Sign in", use_container_width=True)

    if submitted:
        try:
            db = get_firestore_client(project_id)
            id_token, _principals = authenticate_with_password(
                email, password, api_key, project_id, db
            )
        except FirebaseAuthError as exc:
            st.error(str(exc))
        except Exception:
            logger.exception("Firebase sign-in flow failed")
            st.error("Sign-in could not be completed. Check Firebase configuration and try again.")
        else:
            st.session_state["firebase_id_token"] = id_token
            st.rerun()
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
    st.markdown("**How to experience-**")
    st.markdown(
        "🟢 Below - Join Tenant A"

    )
    project_id = firebase_project_id()
    st.markdown("🟢 Ask away - Get info about me")
    st.markdown("🟢 Check if you getting the right data.")
    principal = render_authentication(project_id, firebase_web_api_key())
    st.divider()
    st.caption("Local learning build · tenant-scoped workspace")

if principal and project_id:
    render_chat(principal, project_id)
    st.stop()
else:
    st.markdown(
        """
        <section class="hero">
            <div class="eyebrow">Recruiter workspace · Tenant A</div>
            <h1>Candidate knowledge, with access built in.</h1>
            <p>Explore experience, skills, projects, and outcomes from approved profiles. New accounts start with employee access; HR-only information remains restricted.</p>
        </section>
        """,
        unsafe_allow_html=True,
    )

    st.write("")

    status_col, boundary_col, audit_col = st.columns(3)
    with status_col:
        st.markdown(
            '<div class="card"><h3>🏢 Tenant A workspace</h3><div class="muted">Your account is assigned to Tenant A. Access starts at employee level; HR roles are granted separately.</div></div>',
            unsafe_allow_html=True,
        )
    with boundary_col:
        st.markdown(
            '<div class="card"><h3>🧑‍💼 Candidate profile</h3><div class="muted">Professional experience and skills are in Tenant A; education details are stored separately.</div></div>',
            unsafe_allow_html=True,
        )
    with audit_col:
        st.markdown(
            '<div class="card"><h3>🔒 Tenant boundary</h3><div class="muted">Education details belong to Tenant B and cannot be retrieved from a Tenant A session.</div></div>',
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

    st.info(
        "Sign in to ask questions about the data seeded into your selected tenant. "
        "The resume is contact-redacted; its education section is available only in Tenant B."
    )
