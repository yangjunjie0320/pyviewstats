"""Tests for utils/crypto.py — AES-GCM decryption."""

import json

import pytest
from Crypto.Cipher import AES

from src.crypto import _KEY, _IV, _decode_byte_array, decrypt_payload


class TestDecodeByteArray:
    """Test the base64 → JSON int array → bytes conversion."""

    def test_positive_values(self) -> None:
        import base64

        arr = [65, 66, 67]  # 'A', 'B', 'C'
        b64 = base64.b64encode(json.dumps(arr).encode()).decode()
        assert _decode_byte_array(b64) == b"ABC"

    def test_negative_values_wrap(self) -> None:
        """Negative values should wrap via modulo 256."""
        import base64

        arr = [-1, -128, 256, 0]  # 255, 128, 0, 0
        b64 = base64.b64encode(json.dumps(arr).encode()).decode()
        result = _decode_byte_array(b64)
        assert result == bytes([255, 128, 0, 0])


class TestDecryptPayload:
    """Test decrypt_payload with known key/IV."""

    def _encrypt(self, plaintext_dict: dict) -> bytes:
        """Encrypt using the same key/IV to produce valid test ciphertext."""
        plaintext = json.dumps(plaintext_dict).encode("utf-8")
        cipher = AES.new(_KEY, AES.MODE_GCM, nonce=_IV)
        ciphertext, tag = cipher.encrypt_and_digest(plaintext)
        return ciphertext + tag

    def test_roundtrip(self) -> None:
        """Encrypt then decrypt should return original dict."""
        original = {"data": [{"rank": 1, "video": {"videoId": "abc123"}}]}
        encrypted = self._encrypt(original)
        result = decrypt_payload(encrypted)
        assert result == original

    def test_empty_dict_roundtrip(self) -> None:
        encrypted = self._encrypt({})
        assert decrypt_payload(encrypted) == {}

    def test_ciphertext_too_short(self) -> None:
        with pytest.raises(ValueError, match="too short"):
            decrypt_payload(b"short")

    def test_ciphertext_exactly_16_bytes(self) -> None:
        with pytest.raises(ValueError, match="too short"):
            decrypt_payload(b"x" * 16)

    def test_tampered_tag_raises(self) -> None:
        """Flipping a bit in the GCM tag should cause verification failure."""
        encrypted = self._encrypt({"key": "value"})
        tampered = encrypted[:-1] + bytes([encrypted[-1] ^ 0xFF])
        with pytest.raises((ValueError, Exception)):
            decrypt_payload(tampered)

    def test_key_and_iv_are_correct_length(self) -> None:
        """AES-256 key should be 32 bytes, GCM nonce should be 16 bytes."""
        assert len(_KEY) == 32
        assert len(_IV) == 16
