import os
import unittest
from unittest.mock import patch

from cryptography.fernet import Fernet

from services.credential_cipher import CredentialCipher, PREFIX


class CredentialCipherTestCase(unittest.TestCase):
    def test_encrypts_and_decrypts_spreadsheet_password(self):
        key = Fernet.generate_key().decode("ascii")
        with patch.dict(os.environ, {"SPREADSHEET_CREDENTIAL_KEY": key}):
            cipher = CredentialCipher()
            encrypted = cipher.encrypt("senha-demo")

        self.assertTrue(encrypted.startswith(PREFIX))
        self.assertNotIn("senha-demo", encrypted)
        self.assertEqual(cipher.decrypt(encrypted), "senha-demo")

    def test_keeps_legacy_plaintext_readable_for_migration(self):
        key = Fernet.generate_key().decode("ascii")
        with patch.dict(os.environ, {"SPREADSHEET_CREDENTIAL_KEY": key}):
            cipher = CredentialCipher()

        self.assertEqual(cipher.decrypt("legado"), "legado")


if __name__ == "__main__":
    unittest.main()
