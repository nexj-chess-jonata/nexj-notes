"""Núcleo do Cofre de Notas: criptografia, lixeira e destruição definitiva.

Arquitetura:
- A senha gera uma chave (KEK) via PBKDF2-HMAC-SHA256.
- A KEK protege uma chave de dados aleatória (DEK).
- As notas ficam criptografadas com a DEK (Fernet = AES-128-CBC + HMAC).
- Tudo fica em UM arquivo (vault.bin), gravado de forma atômica.
- Ao DESTRUIR uma nota, a DEK é trocada por uma nova e o arquivo antigo é
  sobrescrito com bytes aleatórios: cópias antigas ficam indecifráveis.
"""
import base64
import json
import os
import secrets
import time
import uuid

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

ITERATIONS = 390_000
MIN_PASSWORD = 6
TRASH_DAYS = 30


class WrongPassword(Exception):
    pass


class WeakPassword(Exception):
    pass


class Vault:
    def __init__(self, folder):
        self.folder = folder
        os.makedirs(folder, exist_ok=True)
        self.path = os.path.join(folder, "vault.bin")
        self.tmp = self.path + ".tmp"
        self._kek = None  # bytes (base64 urlsafe)
        self._dek = None
        self._salt = None
        self._iter = ITERATIONS
        self.data = None
        self.on_kek_changed = None  # callback(kek_b64) quando a senha muda

    # ---------- estado ----------
    def exists(self):
        return os.path.exists(self.path) or os.path.exists(self.tmp)

    @property
    def unlocked(self):
        return self.data is not None

    def lock(self):
        self._kek = self._dek = None
        self.data = None

    # ---------- chaves ----------
    @staticmethod
    def _derive(password, salt, iterations):
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(), length=32, salt=salt, iterations=iterations
        )
        return base64.urlsafe_b64encode(kdf.derive(password.encode("utf-8")))

    def export_kek(self):
        return self._kek.decode()

    # ---------- arquivo ----------
    def _read_raw(self):
        for p in (self.path, self.tmp):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (OSError, ValueError):
                continue
        raise WrongPassword("cofre ilegível")

    def _shred(self, path):
        """Sobrescreve o arquivo com bytes aleatórios e remove."""
        try:
            size = os.path.getsize(path)
            with open(path, "r+b") as f:
                for _ in range(2):
                    f.seek(0)
                    f.write(secrets.token_bytes(max(size, 1)))
                    f.flush()
                    os.fsync(f.fileno())
            os.remove(path)
        except OSError:
            pass

    def _write(self, rotate=False):
        if rotate:
            self._dek = Fernet.generate_key()
        wrapped = Fernet(self._kek).encrypt(self._dek).decode()
        blob = Fernet(self._dek).encrypt(
            json.dumps(self.data, ensure_ascii=False).encode("utf-8")
        ).decode()
        doc = {
            "v": 1,
            "salt": base64.b64encode(self._salt).decode(),
            "iter": self._iter,
            "wrapped_dek": wrapped,
            "data": blob,
        }
        with open(self.tmp, "w", encoding="utf-8") as f:
            json.dump(doc, f)
            f.flush()
            os.fsync(f.fileno())
        if os.path.exists(self.path):
            self._shred(self.path)
        os.replace(self.tmp, self.path)

    # ---------- criar / abrir ----------
    def create(self, password):
        if len(password) < MIN_PASSWORD:
            raise WeakPassword(f"Use pelo menos {MIN_PASSWORD} caracteres.")
        self._salt = secrets.token_bytes(16)
        self._iter = ITERATIONS
        self._kek = self._derive(password, self._salt, self._iter)
        self._dek = Fernet.generate_key()
        self.data = {"notes": []}
        self._write()

    def unlock(self, password):
        doc = self._read_raw()
        salt = base64.b64decode(doc["salt"])
        kek = self._derive(password, salt, doc["iter"])
        self._open(doc, kek)

    def unlock_with_kek(self, kek_b64):
        self._open(self._read_raw(), kek_b64.encode())

    def _open(self, doc, kek):
        try:
            dek = Fernet(kek).decrypt(doc["wrapped_dek"].encode())
            raw = Fernet(dek).decrypt(doc["data"].encode())
        except (InvalidToken, ValueError):
            raise WrongPassword("Senha incorreta.")
        self._kek, self._dek = kek, dek
        self._salt = base64.b64decode(doc["salt"])
        self._iter = doc["iter"]
        self.data = json.loads(raw.decode("utf-8"))
        if self.purge_expired():
            pass

    def change_password(self, old, new):
        if len(new) < MIN_PASSWORD:
            raise WeakPassword(f"Use pelo menos {MIN_PASSWORD} caracteres.")
        doc = self._read_raw()
        salt = base64.b64decode(doc["salt"])
        if self._derive(old, salt, doc["iter"]) != self._kek:
            raise WrongPassword("Senha atual incorreta.")
        self._salt = secrets.token_bytes(16)
        self._kek = self._derive(new, self._salt, self._iter)
        self._write(rotate=True)
        if self.on_kek_changed:
            self.on_kek_changed(self.export_kek())

    # ---------- notas ----------
    def _find(self, nid):
        for n in self.data["notes"]:
            if n["id"] == nid:
                return n
        return None

    def notes(self):
        r = [n for n in self.data["notes"] if not n.get("deleted")]
        return sorted(r, key=lambda n: n["updated"], reverse=True)

    def trashed(self):
        r = [n for n in self.data["notes"] if n.get("deleted")]
        return sorted(r, key=lambda n: n["deleted"], reverse=True)

    def get(self, nid):
        return self._find(nid)

    def save_note(self, nid, title, body):
        now = time.time()
        n = self._find(nid) if nid else None
        if n:
            n["title"], n["body"], n["updated"] = title, body, now
        else:
            nid = uuid.uuid4().hex
            self.data["notes"].append(
                {"id": nid, "title": title, "body": body,
                 "created": now, "updated": now, "deleted": None}
            )
        self._write()
        return nid

    def trash(self, nid):
        n = self._find(nid)
        if n:
            n["deleted"] = time.time()
            self._write()

    def restore(self, nid):
        n = self._find(nid)
        if n:
            n["deleted"] = None
            self._write()

    def destroy(self, nid):
        """Destruição definitiva: remove a nota e troca a chave de dados."""
        self.data["notes"] = [n for n in self.data["notes"] if n["id"] != nid]
        self._write(rotate=True)

    def empty_trash(self):
        self.data["notes"] = [n for n in self.data["notes"] if not n.get("deleted")]
        self._write(rotate=True)

    def purge_expired(self, days=TRASH_DAYS):
        limit = time.time() - days * 86400
        keep = [n for n in self.data["notes"]
                if not (n.get("deleted") and n["deleted"] < limit)]
        if len(keep) != len(self.data["notes"]):
            self.data["notes"] = keep
            self._write(rotate=True)
            return True
        return False

    def wipe_all(self):
        """Destrói o cofre inteiro. Irreversível."""
        for p in (self.path, self.tmp):
            if os.path.exists(p):
                self._shred(p)
        self.lock()
