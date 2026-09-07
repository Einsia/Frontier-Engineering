"""Trusted reference implementations for the Cryptographic benchmarks.

The point of this module is that the *scorer* owns the answer key. The three
Cryptographic benchmarks (AES-128-CTR, SHA-256, SHA3-256) are the rare case
where a candidate's output can be checked against a published standard rather
than against something the candidate itself produced, so there is no reason for
the evaluator ever to take the candidate's word for correctness.

Everything here runs inside the scoring process and is imported *before* any
candidate binary is compiled or executed. The reference outputs for a run are
computed up front and held in memory, so by the time the candidate runs there is
nothing left on disk for it to influence.

Sources for the known-answer tests below:

* AES-128 single block -- FIPS-197 Appendix B / C.1.
* AES-128-CTR          -- NIST SP 800-38A section F.5.1.
* SHA-256              -- FIPS-180-4 Appendix B.
* SHA3-256             -- FIPS-202 / NIST CSRC example values.

``selftest()`` runs every one of them and raises. A scorer that cannot verify
its own reference must refuse to score, not fall back to trusting the candidate.
"""

from __future__ import annotations

import hashlib
from typing import Callable

__all__ = [
    "aes128_ctr_encrypt",
    "sha256_hex",
    "sha3_256_hex",
    "selftest",
    "aes_backend_name",
]


# ---------------------------------------------------------------------------
# AES-128 (pure Python, no third-party dependency)
# ---------------------------------------------------------------------------

_SBOX = bytes.fromhex(
    "637c777bf26b6fc53001672bfed7ab76"
    "ca82c97dfa5947f0add4a2af9ca472c0"
    "b7fd9326363ff7cc34a5e5f171d83115"
    "04c723c31896059a071280e2eb27b275"
    "09832c1a1b6e5aa0523bd6b329e32f84"
    "53d100ed20fcb15b6acbbe394a4c58cf"
    "d0efaafb434d338545f9027f503c9fa8"
    "51a3408f929d38f5bcb6da2110fff3d2"
    "cd0c13ec5f974417c4a77e3d645d1973"
    "60814fdc222a908846eeb814de5e0bdb"
    "e0323a0a4906245cc2d3ac629195e479"
    "e7c8376d8dd54ea96c56f4ea657aae08"
    "ba78252e1ca6b4c6e8dd741f4bbd8b8a"
    "703eb5664803f60e613557b986c11d9e"
    "e1f8981169d98e949b1e87e9ce5528df"
    "8ca1890dbfe6426841992d0fb054bb16"
)

_RCON = (0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1B, 0x36)


def _xtime(a: int) -> int:
    a <<= 1
    if a & 0x100:
        a = (a ^ 0x1B) & 0xFF
    return a


def _build_tables() -> tuple[list[int], list[int]]:
    """T-table for the main rounds and the plain S-box table for the last."""
    te = []
    te_last = []
    for x in range(256):
        s = _SBOX[x]
        s2 = _xtime(s)
        s3 = s2 ^ s
        # Column layout matches the big-endian word packing used below.
        te.append((s2 << 24) | (s << 16) | (s << 8) | s3)
        te_last.append((s << 24) | (s << 16) | (s << 8) | s)
    return te, te_last


_TE, _TE_LAST = _build_tables()
_MASK = 0xFFFFFFFF


def _rotl32(x: int, n: int) -> int:
    return ((x << n) | (x >> (32 - n))) & _MASK


def _expand_key(key: bytes) -> list[int]:
    if len(key) != 16:
        raise ValueError(f"AES-128 needs a 16-byte key, got {len(key)}")
    w = [int.from_bytes(key[i : i + 4], "big") for i in range(0, 16, 4)]
    for i in range(4, 44):
        t = w[i - 1]
        if i % 4 == 0:
            t = _rotl32(t, 8)
            t = (
                (_SBOX[(t >> 24) & 0xFF] << 24)
                | (_SBOX[(t >> 16) & 0xFF] << 16)
                | (_SBOX[(t >> 8) & 0xFF] << 8)
                | _SBOX[t & 0xFF]
            )
            t ^= _RCON[i // 4 - 1] << 24
        w.append(w[i - 4] ^ t)
    return w


def _encrypt_block_words(w: list[int], block: bytes) -> bytes:
    s0 = int.from_bytes(block[0:4], "big") ^ w[0]
    s1 = int.from_bytes(block[4:8], "big") ^ w[1]
    s2 = int.from_bytes(block[8:12], "big") ^ w[2]
    s3 = int.from_bytes(block[12:16], "big") ^ w[3]

    te = _TE
    k = 4
    for _ in range(9):
        t0 = (
            te[(s0 >> 24) & 0xFF]
            ^ _rotl32(te[(s1 >> 16) & 0xFF], 24)
            ^ _rotl32(te[(s2 >> 8) & 0xFF], 16)
            ^ _rotl32(te[s3 & 0xFF], 8)
        ) ^ w[k]
        t1 = (
            te[(s1 >> 24) & 0xFF]
            ^ _rotl32(te[(s2 >> 16) & 0xFF], 24)
            ^ _rotl32(te[(s3 >> 8) & 0xFF], 16)
            ^ _rotl32(te[s0 & 0xFF], 8)
        ) ^ w[k + 1]
        t2 = (
            te[(s2 >> 24) & 0xFF]
            ^ _rotl32(te[(s3 >> 16) & 0xFF], 24)
            ^ _rotl32(te[(s0 >> 8) & 0xFF], 16)
            ^ _rotl32(te[s1 & 0xFF], 8)
        ) ^ w[k + 2]
        t3 = (
            te[(s3 >> 24) & 0xFF]
            ^ _rotl32(te[(s0 >> 16) & 0xFF], 24)
            ^ _rotl32(te[(s1 >> 8) & 0xFF], 16)
            ^ _rotl32(te[s2 & 0xFF], 8)
        ) ^ w[k + 3]
        s0, s1, s2, s3 = t0, t1, t2, t3
        k += 4

    sb = _SBOX
    out0 = (
        (sb[(s0 >> 24) & 0xFF] << 24)
        | (sb[(s1 >> 16) & 0xFF] << 16)
        | (sb[(s2 >> 8) & 0xFF] << 8)
        | sb[s3 & 0xFF]
    ) ^ w[40]
    out1 = (
        (sb[(s1 >> 24) & 0xFF] << 24)
        | (sb[(s2 >> 16) & 0xFF] << 16)
        | (sb[(s3 >> 8) & 0xFF] << 8)
        | sb[s0 & 0xFF]
    ) ^ w[41]
    out2 = (
        (sb[(s2 >> 24) & 0xFF] << 24)
        | (sb[(s3 >> 16) & 0xFF] << 16)
        | (sb[(s0 >> 8) & 0xFF] << 8)
        | sb[s1 & 0xFF]
    ) ^ w[42]
    out3 = (
        (sb[(s3 >> 24) & 0xFF] << 24)
        | (sb[(s0 >> 16) & 0xFF] << 16)
        | (sb[(s1 >> 8) & 0xFF] << 8)
        | sb[s2 & 0xFF]
    ) ^ w[43]
    return (
        out0.to_bytes(4, "big")
        + out1.to_bytes(4, "big")
        + out2.to_bytes(4, "big")
        + out3.to_bytes(4, "big")
    )


def aes128_encrypt_block(key: bytes, block: bytes) -> bytes:
    """Single-block AES-128 encryption (ECB of one block), pure Python."""
    if len(block) != 16:
        raise ValueError(f"AES block must be 16 bytes, got {len(block)}")
    return _encrypt_block_words(_expand_key(key), block)


def _aes128_ctr_pure(key: bytes, iv: bytes, data: bytes) -> bytes:
    """AES-128-CTR with the full 16-byte IV as a big-endian 128-bit counter.

    This is what OpenSSL's ``EVP_aes_128_ctr`` does, which is what the shipped
    ``verification/validate.cpp`` used as its oracle.
    """
    if len(iv) != 16:
        raise ValueError(f"AES-CTR needs a 16-byte IV, got {len(iv)}")
    w = _expand_key(key)
    counter = int.from_bytes(iv, "big")
    out = bytearray(len(data))
    encrypt = _encrypt_block_words
    for offset in range(0, len(data), 16):
        ks = encrypt(w, counter.to_bytes(16, "big"))
        counter = (counter + 1) & ((1 << 128) - 1)
        chunk = data[offset : offset + 16]
        end = offset + len(chunk)
        out[offset:end] = bytes(a ^ b for a, b in zip(chunk, ks))
    return bytes(out)


def _load_fast_aes() -> tuple[str, Callable[[bytes, bytes, bytes], bytes] | None]:
    """Prefer a C implementation for speed; the pure-Python one is the anchor.

    Whichever backend is used, ``selftest()`` checks it against the published
    vectors *and* against the pure-Python implementation, so a broken or
    surprising backend is a hard failure rather than a silent wrong answer key.
    """
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    except Exception:
        return "pure-python", None

    def _run(key: bytes, iv: bytes, data: bytes) -> bytes:
        encryptor = Cipher(algorithms.AES(key), modes.CTR(iv)).encryptor()
        return encryptor.update(data) + encryptor.finalize()

    return "cryptography", _run


_AES_BACKEND_NAME, _AES_FAST = _load_fast_aes()


def aes_backend_name() -> str:
    return _AES_BACKEND_NAME


def aes128_ctr_encrypt(key: bytes, iv: bytes, data: bytes) -> bytes:
    if _AES_FAST is not None:
        return _AES_FAST(key, iv, data)
    return _aes128_ctr_pure(key, iv, data)


# ---------------------------------------------------------------------------
# SHA-256 / SHA3-256
# ---------------------------------------------------------------------------


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha3_256_hex(data: bytes) -> str:
    return hashlib.sha3_256(data).hexdigest()


# ---------------------------------------------------------------------------
# Known-answer tests
# ---------------------------------------------------------------------------

# FIPS-197 Appendix C.1 (AES-128 single block).
_FIPS197_KEY = bytes.fromhex("000102030405060708090a0b0c0d0e0f")
_FIPS197_PT = bytes.fromhex("00112233445566778899aabbccddeeff")
_FIPS197_CT = bytes.fromhex("69c4e0d86a7b0430d8cdb78070b4c55a")

# NIST SP 800-38A F.5.1 CTR-AES128.Encrypt.
_SP80038A_KEY = bytes.fromhex("2b7e151628aed2a6abf7158809cf4f3c")
_SP80038A_IV = bytes.fromhex("f0f1f2f3f4f5f6f7f8f9fafbfcfdfeff")
_SP80038A_PT = bytes.fromhex(
    "6bc1bee22e409f96e93d7e117393172a"
    "ae2d8a571e03ac9c9eb76fac45af8e51"
    "30c81c46a35ce411e5fbc1191a0a52ef"
    "f69f2445df4f9b17ad2b417be66c3710"
)
_SP80038A_CT = bytes.fromhex(
    "874d6191b620e3261bef6864990db6ce"
    "9806f66b7970fdff8617187bb9fffdff"
    "5ae4df3edbd5d35e5b4f09020db03eab"
    "1e031dda2fbe03d1792170a0f3009cee"
)

_SHA256_VECTORS = (
    (b"", "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"),
    (b"abc", "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"),
    (
        b"abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq",
        "248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1",
    ),
)

_SHA3_256_VECTORS = (
    (b"", "a7ffc6f8bf1ed76651c14756a061d662f580ff4de43b49fa82d80a4b80f8434a"),
    (b"abc", "3a985da74fe225b2045c172d6bd390bd855f086e3e9d525b46bfe24511431532"),
    (
        b"abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq",
        "41c0dba2a9d6240849100376a8235e2c82e1b9998a999e21db32dd97496d3376",
    ),
)


class ReferenceSelfTestError(RuntimeError):
    """The scorer's own reference disagrees with the published standard."""


def selftest() -> None:
    """Verify every reference against published vectors. Raises on any mismatch."""
    got = aes128_encrypt_block(_FIPS197_KEY, _FIPS197_PT)
    if got != _FIPS197_CT:
        raise ReferenceSelfTestError(
            f"FIPS-197 AES block KAT failed: {got.hex()} != {_FIPS197_CT.hex()}"
        )

    pure = _aes128_ctr_pure(_SP80038A_KEY, _SP80038A_IV, _SP80038A_PT)
    if pure != _SP80038A_CT:
        raise ReferenceSelfTestError(
            f"SP800-38A CTR KAT failed (pure python): {pure.hex()} != {_SP80038A_CT.hex()}"
        )
    active = aes128_ctr_encrypt(_SP80038A_KEY, _SP80038A_IV, _SP80038A_PT)
    if active != _SP80038A_CT:
        raise ReferenceSelfTestError(
            f"SP800-38A CTR KAT failed ({_AES_BACKEND_NAME}): {active.hex()}"
        )

    # Cross-check the fast backend against the pure implementation on a
    # non-block-aligned length and on a counter that wraps within the low word.
    if _AES_FAST is not None:
        probe_key = bytes(range(16))
        probe_iv = bytes.fromhex("00000000000000000000000000fffffe")
        probe_data = bytes(range(256)) * 3 + b"\x01\x02\x03"
        if _AES_FAST(probe_key, probe_iv, probe_data) != _aes128_ctr_pure(
            probe_key, probe_iv, probe_data
        ):
            raise ReferenceSelfTestError(
                f"AES backend '{_AES_BACKEND_NAME}' disagrees with the pure-Python reference"
            )

    for data, expected in _SHA256_VECTORS:
        if sha256_hex(data) != expected:
            raise ReferenceSelfTestError(f"SHA-256 KAT failed for {data!r}")
    for data, expected in _SHA3_256_VECTORS:
        if sha3_256_hex(data) != expected:
            raise ReferenceSelfTestError(f"SHA3-256 KAT failed for {data!r}")


# Fail at import time rather than mid-score.
selftest()
