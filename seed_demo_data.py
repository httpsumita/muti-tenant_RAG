from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from dotenv import load_dotenv
from google.api_core.exceptions import GoogleAPICallError
from google.cloud.firestore_v1.vector import Vector

from firebase_client import get_firestore_client
from gemini_provider import GeminiProvider
from ingestion import load_text_file
from models import Document


ROOT = Path(__file__).resolve().parent
TENANT_A_ID = "tenant-a"
TENANT_B_ID = "tenant-b"
SEED_OWNER_ID = "public-demo-seed"
PROFILE_DOCUMENT_ID = "DOC-TENA-RESUME-001"
EDUCATION_DOCUMENT_ID = "DOC-TENB-EDU-001"
LEGACY_POLICY_DOCUMENT_ID = "DOC-TENA-001"
PROFILE_SOURCE = ROOT / "knowledge" / "tenant-a-resume.txt"
EDUCATION_SOURCE = ROOT / "knowledge" / "tenant-b-education.txt"


def _queue_legacy_policy_deletes(db, batch) -> int:
    snapshots = (
        db.collection("chunks")
        .where("tenant_id", "==", TENANT_A_ID)
        .stream()
    )
    deleted_chunks = 0
    for snapshot in snapshots:
        data = snapshot.to_dict() or {}
        if data.get("document_id") == LEGACY_POLICY_DOCUMENT_ID:
            batch.delete(snapshot.reference)
            deleted_chunks += 1

    old_document_ref = db.collection("documents").document(LEGACY_POLICY_DOCUMENT_ID)
    old_document = old_document_ref.get()
    old_document_data = old_document.to_dict() or {}
    if old_document.exists and old_document_data.get("tenant_id") == TENANT_A_ID:
        batch.delete(old_document_ref)
        deleted_chunks += 1
    return deleted_chunks


def seed_demo_data(
    db,
    *,
    embed_documents: Callable[[list[str]], tuple[tuple[float, ...], ...]],
    replace_legacy_policy: bool = False,
) -> tuple[int, int]:
    """Seed professional experience in tenant-a and education only in tenant-b."""
    profile_ref = db.collection("documents").document(PROFILE_DOCUMENT_ID)
    education_ref = db.collection("documents").document(EDUCATION_DOCUMENT_ID)
    created_at = datetime.now(timezone.utc)
    existing_profile = profile_ref.get().to_dict() or {}
    existing_education = education_ref.get().to_dict() or {}
    profile_document = Document(
        document_id=PROFILE_DOCUMENT_ID,
        tenant_id=TENANT_A_ID,
        title="Sumita Pathak · Professional Profile",
        owner_id=SEED_OWNER_ID,
        allowed_roles={"employee"},
        created_at=existing_profile.get("created_at") or created_at,
    )
    education_document = Document(
        document_id=EDUCATION_DOCUMENT_ID,
        tenant_id=TENANT_B_ID,
        title="Education and Recognition",
        owner_id=SEED_OWNER_ID,
        allowed_roles={"employee"},
        created_at=existing_education.get("created_at") or created_at,
    )
    profile_chunks = load_text_file(PROFILE_SOURCE, profile_document)
    education_chunks = load_text_file(EDUCATION_SOURCE, education_document)
    all_chunks = profile_chunks + education_chunks
    vectors = embed_documents([chunk.text for chunk in all_chunks])
    if len(vectors) != len(all_chunks) or any(len(vector) != 768 for vector in vectors):
        raise ValueError("Gemini embeddings must match the chunk count and be 768-dimensional")

    batch = db.batch()
    if replace_legacy_policy:
        _queue_legacy_policy_deletes(db, batch)

    for tenant_id, document_id, document_ref, document, chunks in (
        (TENANT_A_ID, PROFILE_DOCUMENT_ID, profile_ref, profile_document, profile_chunks),
        (TENANT_B_ID, EDUCATION_DOCUMENT_ID, education_ref, education_document, education_chunks),
    ):
        current_chunk_ids = {chunk.chunk_id for chunk in chunks}
        old_chunks = db.collection("chunks").where("tenant_id", "==", tenant_id).stream()
        for snapshot in old_chunks:
            data = snapshot.to_dict() or {}
            if data.get("document_id") == document_id and snapshot.id not in current_chunk_ids:
                batch.delete(snapshot.reference)

        batch.set(
            document_ref,
            {
                "document_id": document.document_id,
                "tenant_id": document.tenant_id,
                "title": document.title,
                "owner_id": document.owner_id,
                "allowed_roles": sorted(document.allowed_roles),
                "created_at": document.created_at,
                "status": "active",
                "version": 1,
                "source": "owner-provided resume with contact details omitted",
            },
            merge=True,
        )

    for chunk, vector in zip(all_chunks, vectors, strict=True):
        batch.set(
            db.collection("chunks").document(chunk.chunk_id),
            {
                "chunk_id": chunk.chunk_id,
                "document_id": chunk.document_id,
                "tenant_id": chunk.tenant_id,
                "chunk_index": chunk.chunk_index,
                "text": chunk.text,
                "allowed_roles": sorted(chunk.allowed_roles),
                "embedding": Vector(vector),
            },
            merge=True,
        )
    batch.commit()
    return len(profile_chunks), len(education_chunks)


def main(argv: list[str] | None = None) -> int:
    load_dotenv(".env")
    parser = argparse.ArgumentParser(
        description="Seed Tenant A with professional experience and Tenant B with education details."
    )
    parser.add_argument(
        "--replace-legacy-policy",
        action="store_true",
        help="Delete only the known DOC-TENA-001 fake policy document and its Tenant A chunks.",
    )
    args = parser.parse_args(argv)

    project_id = os.getenv("FIREBASE_PROJECT_ID")
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not project_id:
        parser.error("FIREBASE_PROJECT_ID must be set in .env or the process environment")
    if not api_key:
        parser.error("GEMINI_API_KEY must be set before generating document embeddings")

    try:
        profile_chunks, education_chunks = seed_demo_data(
            get_firestore_client(project_id),
            embed_documents=GeminiProvider(api_key).embed_documents,
            replace_legacy_policy=args.replace_legacy_policy,
        )
    except GoogleAPICallError:
        print(
            "Seeding failed. Check Firestore availability, IAM permissions, and the vector index.",
            file=sys.stderr,
        )
        return 1
    except (OSError, ValueError) as exc:
        print(f"Seeding failed: {exc}", file=sys.stderr)
        return 1

    print(
        "Seeded Tenant A professional-profile chunks: "
        f"{profile_chunks}; Tenant B education chunks: {education_chunks}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())