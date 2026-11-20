"""Envelope encryption (SPEC 12): a fresh AES-256-GCM data key per record, wrapped with the
master key. The master key comes from the environment (never the repo); swapping the wrap/unwrap
step for a KMS call is the only change needed to move it into AWS/GCP KMS."""

import base64
import os
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_VERSION = b"\x01"
_NONCE = 12
_KEY = 32


class CryptoError(Exception):
    pass


def generate_master_key() -> str:
    return base64.urlsafe_b64encode(os.urandom(_KEY)).decode()


@dataclass(frozen=True)
class EnvelopeCipher:
    master_key: bytes

    def __post_init__(self) -> None:
        if len(self.master_key) != _KEY:
            raise CryptoError("master key must be 32 bytes")

    @classmethod
    def from_b64(cls, value: str) -> "EnvelopeCipher":
        if not value:
            raise CryptoError("MASTER_KEY is not configured (run `softtrade gen-master-key`)")
        try:
            return cls(base64.urlsafe_b64decode(value))
        except ValueError as e:
            raise CryptoError("MASTER_KEY is not valid base64") from e

    def encrypt(self, plaintext: bytes, aad: bytes = b"") -> bytes:
        """aad binds the ciphertext to its record (e.g. b"account:<id>:api_key")."""
        data_key, n1, n2 = AESGCM.generate_key(256), os.urandom(_NONCE), os.urandom(_NONCE)
        wrapped = AESGCM(self.master_key).encrypt(n1, data_key, aad)
        body = AESGCM(data_key).encrypt(n2, plaintext, aad)
        return _VERSION + n1 + wrapped + n2 + body

    def decrypt(self, blob: bytes, aad: bytes = b"") -> bytes:
        try:
            if blob[:1] != _VERSION:
                raise CryptoError("unknown ciphertext version")
            n1 = blob[1 : 1 + _NONCE]
            wrapped = blob[1 + _NONCE : 1 + _NONCE + _KEY + 16]
            rest = blob[1 + _NONCE + _KEY + 16 :]
            data_key = AESGCM(self.master_key).decrypt(n1, wrapped, aad)
            return AESGCM(data_key).decrypt(rest[:_NONCE], rest[_NONCE:], aad)
        except (InvalidTag, ValueError) as e:
            raise CryptoError("decryption failed (wrong key, wrong record or tampered data)") from e
