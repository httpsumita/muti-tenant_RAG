import unittest
from unittest.mock import Mock, patch

from firebase_client import get_firestore_client


class FirebaseClientTests(unittest.TestCase):
    @patch("firebase_client.firestore.client")
    @patch("firebase_client.firebase_admin.initialize_app")
    @patch("firebase_client.firebase_admin.get_app", side_effect=ValueError)
    @patch("firebase_client.credentials.Certificate")
    @patch("firebase_client._service_account_info")
    def test_uses_streamlit_service_account_secret(
        self, service_account_info, certificate, get_app, initialize_app, firestore_client
    ) -> None:
        service_account = {"type": "service_account", "project_id": "test-project"}
        service_account_info.return_value = service_account
        certificate.return_value = "service-account-credential"
        app = Mock(project_id="test-project")
        initialize_app.return_value = app

        result = get_firestore_client("test-project")

        certificate.assert_called_once_with(service_account)
        initialize_app.assert_called_once_with(
            credential="service-account-credential",
            options={"projectId": "test-project"},
        )
        firestore_client.assert_called_once_with(app=app)
        self.assertIs(result, firestore_client.return_value)

    @patch("firebase_client.firestore.client")
    @patch("firebase_client.firebase_admin.initialize_app")
    @patch("firebase_client.firebase_admin.get_app", side_effect=ValueError)
    @patch("firebase_client.credentials.ApplicationDefault")
    @patch("firebase_client._service_account_info", return_value=None)
    def test_falls_back_to_adc_when_service_account_secret_is_absent(
        self, service_account_info, application_default, get_app, initialize_app, firestore_client
    ) -> None:
        application_default.return_value = "adc-credential"
        app = Mock(project_id="test-project")
        initialize_app.return_value = app

        get_firestore_client("test-project")

        initialize_app.assert_called_once_with(
            credential="adc-credential",
            options={"projectId": "test-project"},
        )

    def test_rejects_empty_project_id(self) -> None:
        with self.assertRaisesRegex(ValueError, "project ID"):
            get_firestore_client(" ")


if __name__ == "__main__":
    unittest.main()
