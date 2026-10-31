from __future__ import annotations

import firebase_admin
from firebase_admin import credentials, firestore


def get_firestore_client(project_id: str):
    if not project_id.strip():
        raise ValueError("A Firebase project ID is required.")

    try:
        app = firebase_admin.get_app()
    except ValueError:
        app = firebase_admin.initialize_app(
            credential=credentials.ApplicationDefault(),
            options={"projectId": project_id},
        )

    if app.project_id and app.project_id != project_id:
        raise RuntimeError("The initialized Firebase app uses a different project ID.")

    return firestore.client(app=app)