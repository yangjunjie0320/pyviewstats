"""AES-GCM decryption for ViewStats API responses.

Constants extracted from ViewStats frontend JS. If decrypt raises ValueError,
they rotated keys — re-extract from their site.
"""

import base64
import json
import logging

from Crypto.Cipher import AES

logger = logging.getLogger(__name__)

_KEY_B64 = (
    "Wy0zLCAtMTEyLCAxNSwgLTEyNCwgLTcxLCAzMywgLTg0LCAxMDksIDU3LCAtMTI3LCA"
    "xMDcsIC00NiwgMTIyLCA0OCwgODIsIC0xMjYsIDQ3LCA3NiwgLTEyNywgNjUsIDc1LCA"
    "xMTMsIC0xMjEsIDg5LCAtNzEsIDUwLCAtODMsIDg2LCA5MiwgLTQ2LCA0OSwgNTZd"
)
_IV_B64 = (
    "Wzk3LCAxMDksIC0xMDAsIC05MCwgMTIyLCAtMTI0LCAxMSwgLTY5LCAtNDIsIDExNSwg"
    "LTU4LCAtNjcsIDQzLCAtNzUsIDMxLCA3NF0="
)


def _decode_byte_array(b64_str: str) -> bytes:
    """Base64 → JSON int array → unsigned bytes."""
    raw_json = base64.b64decode(b64_str)
    int_array: list[int] = json.loads(raw_json)
    return bytes(v % 256 for v in int_array)


# Pre-compute key and IV at module load time
_KEY = _decode_byte_array(_KEY_B64)
_IV = _decode_byte_array(_IV_B64)


def decrypt_payload(ciphertext: bytes) -> dict:
    """Decrypt an AES-GCM encrypted ViewStats API response.

    The last 16 bytes of the ciphertext are the GCM authentication tag.
    Raises ValueError if decryption fails (likely key rotation).
    """
    if len(ciphertext) <= 16:
        raise ValueError(f"Ciphertext too short ({len(ciphertext)} bytes)")

    tag = ciphertext[-16:]
    encrypted_data = ciphertext[:-16]

    cipher = AES.new(_KEY, AES.MODE_GCM, nonce=_IV)
    plaintext = cipher.decrypt_and_verify(encrypted_data, tag)
    return json.loads(plaintext.decode("utf-8"))
