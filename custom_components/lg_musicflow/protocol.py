"""Wire framing for LG Music Flow speakers."""

from __future__ import annotations

import json
import struct
from typing import Any

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

HEADER_PLAINTEXT = 0x00
HEADER_ENCRYPTED = 0x10
HEADER_SIZE = 5

# Shared key used by the legacy Music Flow controller protocol.
AES_KEY = b"4efgvbn m546Uy7kolKrftgbn =-0u&~"
AES_IV = b"54eRty@hkL,;/y9U"


class LGMusicFlowProtocolError(ValueError):
    """Raised when a speaker frame cannot be decoded."""


def encode_frame(payload: dict[str, Any], *, encrypted: bool = True) -> bytes:
    """Encode one JSON request using the speaker's five-byte frame header."""
    plaintext = (
        json.dumps(payload, separators=(",", ":"), ensure_ascii=False) + "\n"
    ).encode("utf-8")

    if encrypted:
        padder = padding.PKCS7(algorithms.AES.block_size).padder()
        padded = padder.update(plaintext) + padder.finalize()
        encryptor = Cipher(algorithms.AES(AES_KEY), modes.CBC(AES_IV)).encryptor()
        body = encryptor.update(padded) + encryptor.finalize()
        frame_type = HEADER_ENCRYPTED
    else:
        body = plaintext
        frame_type = HEADER_PLAINTEXT

    return struct.pack(">BI", frame_type, len(body)) + body


def decode_payload(frame_type: int, body: bytes) -> dict[str, Any]:
    """Decode a frame body after its five-byte header has been consumed."""
    if frame_type & 0xF0 == HEADER_ENCRYPTED:
        if len(body) % (algorithms.AES.block_size // 8):
            raise LGMusicFlowProtocolError("Encrypted frame is not block aligned")
        decryptor = Cipher(algorithms.AES(AES_KEY), modes.CBC(AES_IV)).decryptor()
        padded = decryptor.update(body) + decryptor.finalize()
        unpadder = padding.PKCS7(algorithms.AES.block_size).unpadder()
        try:
            plaintext = unpadder.update(padded) + unpadder.finalize()
        except ValueError as err:
            raise LGMusicFlowProtocolError("Invalid encrypted frame padding") from err
    else:
        plaintext = body

    try:
        decoded = json.loads(plaintext.decode("utf-8").strip())
    except (UnicodeDecodeError, json.JSONDecodeError) as err:
        raise LGMusicFlowProtocolError("Invalid JSON frame") from err
    if not isinstance(decoded, dict):
        raise LGMusicFlowProtocolError("Speaker frame must contain a JSON object")
    return decoded
