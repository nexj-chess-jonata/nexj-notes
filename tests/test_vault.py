import os
import tempfile
import time
import unittest

from vault import Vault, WrongPassword, WeakPassword


class VaultTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.v = Vault(self.dir)
        self.v.create("senha123")

    def reopen(self, pw="senha123"):
        v = Vault(self.dir)
        v.unlock(pw)
        return v

    def test_wrong_password(self):
        with self.assertRaises(WrongPassword):
            Vault(self.dir).unlock("errada")

    def test_weak_password(self):
        with self.assertRaises(WeakPassword):
            Vault(tempfile.mkdtemp()).create("123")

    def test_save_and_reopen(self):
        self.v.save_note(None, "Título", "segredo")
        n = self.reopen().notes()
        self.assertEqual(n[0]["body"], "segredo")

    def test_plaintext_not_on_disk(self):
        self.v.save_note(None, "Título", "texto-muito-secreto")
        with open(os.path.join(self.dir, "vault.bin"), "rb") as f:
            self.assertNotIn(b"texto-muito-secreto", f.read())

    def test_trash_restore_destroy(self):
        nid = self.v.save_note(None, "a", "b")
        self.v.trash(nid)
        self.assertEqual(len(self.v.notes()), 0)
        self.assertEqual(len(self.v.trashed()), 1)
        self.v.restore(nid)
        self.assertEqual(len(self.v.notes()), 1)
        self.v.trash(nid)
        self.v.destroy(nid)
        v = self.reopen()
        self.assertEqual(v.notes() + v.trashed(), [])

    def test_destroy_rotates_key(self):
        nid = self.v.save_note(None, "a", "b")
        with open(os.path.join(self.dir, "vault.bin")) as f:
            old = f.read()
        self.v.destroy(nid)
        with open(os.path.join(self.dir, "vault.bin")) as f:
            new = f.read()
        self.assertNotEqual(old, new)
        # a cópia antiga não abre mais com a chave atual
        import json
        from cryptography.fernet import Fernet, InvalidToken
        with self.assertRaises(InvalidToken):
            Fernet(self.v._dek).decrypt(json.loads(old)["data"].encode())

    def test_change_password(self):
        self.v.save_note(None, "a", "b")
        self.v.change_password("senha123", "outra-senha")
        with self.assertRaises(WrongPassword):
            self.reopen("senha123")
        self.assertEqual(len(self.reopen("outra-senha").notes()), 1)

    def test_kek_unlock(self):
        self.v.save_note(None, "a", "b")
        kek = self.v.export_kek()
        v = Vault(self.dir)
        v.unlock_with_kek(kek)
        self.assertEqual(len(v.notes()), 1)

    def test_purge_expired(self):
        nid = self.v.save_note(None, "a", "b")
        self.v.trash(nid)
        self.v.get(nid)["deleted"] = time.time() - 40 * 86400
        self.assertTrue(self.v.purge_expired())
        self.assertEqual(self.v.trashed(), [])

    def test_wipe_all(self):
        self.v.wipe_all()
        self.assertFalse(self.v.exists())


if __name__ == "__main__":
    unittest.main()
