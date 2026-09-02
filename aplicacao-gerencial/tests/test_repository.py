from __future__ import annotations

import tempfile
import unittest
import os
from pathlib import Path

from database.repository import Repository


class RepositoryTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.previous_bootstrap_username = os.environ.get("GERENCIAL_BOOTSTRAP_ADMIN_USERNAME")
        self.previous_bootstrap_password = os.environ.get("GERENCIAL_BOOTSTRAP_ADMIN_PASSWORD")
        os.environ["GERENCIAL_BOOTSTRAP_ADMIN_USERNAME"] = "admin.bootstrap"
        os.environ["GERENCIAL_BOOTSTRAP_ADMIN_PASSWORD"] = "Senha-Forte-2026"
        database_path = Path(self.temp_dir.name) / "gerencial-test.sqlite3"
        self.repository = Repository(f"sqlite:///{database_path.as_posix()}")

    def tearDown(self) -> None:
        if self.previous_bootstrap_username is None:
            os.environ.pop("GERENCIAL_BOOTSTRAP_ADMIN_USERNAME", None)
        else:
            os.environ["GERENCIAL_BOOTSTRAP_ADMIN_USERNAME"] = self.previous_bootstrap_username
        if self.previous_bootstrap_password is None:
            os.environ.pop("GERENCIAL_BOOTSTRAP_ADMIN_PASSWORD", None)
        else:
            os.environ["GERENCIAL_BOOTSTRAP_ADMIN_PASSWORD"] = self.previous_bootstrap_password
        self.temp_dir.cleanup()

    def test_configured_bootstrap_admin_authenticates_without_exposing_credentials(self) -> None:
        user = self.repository.authenticate_user("admin.bootstrap", "Senha-Forte-2026")

        self.assertIsNotNone(user)
        self.assertEqual(user["role"], "superadmin")
        self.assertNotIn("password_hash", user)
        self.assertIsNone(self.repository.authenticate_user("admin.bootstrap", "senha-invalida"))

    def test_session_is_invalidated_when_user_is_deactivated(self) -> None:
        user = self.repository.create_user("gestor.teste", "segredo", "gerencial")
        token = self.repository.create_session(user["username"])

        self.assertEqual(self.repository.get_user_by_session(token)["id"], user["id"])

        self.repository.set_user_active(user["id"], False)

        self.assertIsNone(self.repository.get_user_by_session(token))
        self.assertIsNone(self.repository.authenticate_user("gestor.teste", "segredo"))

    def test_user_permission_override_wins_over_role_default(self) -> None:
        user = self.repository.create_user("supervisor.teste", "segredo", "supervisor")
        self.assertEqual(user["role"], "supervisor")
        self.assertIsNotNone(self.repository.authenticate_user("supervisor.teste", "segredo"))
        self.assertFalse(self.repository.has_permission("supervisor", "manage_users", user["id"]))

        self.repository.save_user_permission_overrides(user["id"], {"manage_users": True})

        self.assertTrue(self.repository.has_permission("supervisor", "manage_users", user["id"]))
        self.assertFalse(self.repository.has_permission("supervisor", "restore_backup", user["id"]))

    def test_admin_permissions_cannot_be_reduced(self) -> None:
        result = self.repository.save_role_permissions({"roles": {"admin": {"manage_users": False}}})

        self.assertTrue(result["roles"]["admin"]["manage_users"])
        self.assertTrue(self.repository.has_permission("admin", "restore_backup"))

    def test_superadmin_has_full_permissions_and_can_update_admin(self) -> None:
        previous_superadmins = self.repository.active_superadmin_count()
        superadmin = self.repository.create_user("master.teste", "senha-forte", "superadmin")
        admin = self.repository.create_user("admin.teste", "senha-antiga", "admin")

        self.assertTrue(self.repository.has_permission("superadmin", "restore_backup", superadmin["id"]))
        self.assertEqual(self.repository.active_superadmin_count(), previous_superadmins + 1)

        updated = self.repository.update_user(admin["id"], "admin.editado", "admin", "senha-nova")

        self.assertEqual(updated["username"], "admin.editado")
        self.assertEqual(updated["role"], "admin")
        self.assertIsNone(self.repository.authenticate_user("admin.teste", "senha-antiga"))
        self.assertIsNotNone(self.repository.authenticate_user("admin.editado", "senha-nova"))

    def test_update_user_rejects_duplicate_username(self) -> None:
        first = self.repository.create_user("primeiro", "segredo", "gerencial")
        self.repository.create_user("segundo", "segredo", "admin")

        with self.assertRaisesRegex(ValueError, "Ja existe"):
            self.repository.update_user(first["id"], "segundo", "gerencial")

    def test_notes_round_trip(self) -> None:
        created = self.repository.create_note("evento", "42", "Primeira observacao", "gestor.teste")
        updated = self.repository.update_note(created["id"], "Texto revisado", "gestor.teste")
        notes = self.repository.list_notes("evento", "42")

        self.assertEqual(updated["text"], "Texto revisado")
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0]["id"], created["id"])


if __name__ == "__main__":
    unittest.main()
