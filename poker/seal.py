"""Печать колоды: шифрование только на stdlib, совместимое с poker/web/core.js.

Ключ колоды K (32 байта) = K1 XOR K2. K1 уходит в ссылку руководителя, K2 — в ссылку
сотрудника (после «#», на сервер не передаётся). Открыть колоду можно только имея обе
половины — то есть когда оба вошли в комнату.

Схема: enc = HMAC(K, "enc"), mac = HMAC(K, "mac"); поток — SHA-256(enc ‖ nonce ‖ i) по
блокам; tag = HMAC(mac, nonce ‖ ct) (encrypt-then-MAC). Задача печати — процессная:
колоду нельзя прочитать случайно или по одной ссылке. Ограничения — docs/spec-online.md.
"""
import base64
import hashlib
import hmac
import json
import secrets

ALG = "sha256-ctr+hmac-sha256"


def b64u(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def unb64u(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def new_halves():
    """(K, K1, K2): K1 и K2 — случайные, K = K1 XOR K2."""
    k1, k2 = secrets.token_bytes(32), secrets.token_bytes(32)
    return xor(k1, k2), k1, k2


def xor(a, b):
    return bytes(x ^ y for x, y in zip(a, b))


def _keystream(enc, nonce, n):
    out = bytearray()
    i = 0
    while len(out) < n:
        out += hashlib.sha256(enc + nonce + i.to_bytes(4, "big")).digest()
        i += 1
    return bytes(out[:n])


def _subkeys(key):
    return (hmac.new(key, b"enc", hashlib.sha256).digest(),
            hmac.new(key, b"mac", hashlib.sha256).digest())


def seal(obj, key):
    pt = json.dumps(obj, ensure_ascii=False).encode()
    enc, mac = _subkeys(key)
    nonce = secrets.token_bytes(16)
    ct = xor(pt, _keystream(enc, nonce, len(pt)))
    tag = hmac.new(mac, nonce + ct, hashlib.sha256).digest()
    return {"v": 1, "alg": ALG, "nonce": b64u(nonce), "ct": b64u(ct), "tag": b64u(tag)}


def unseal(blob, key):
    if blob.get("alg") != ALG:
        raise ValueError(f"неизвестная печать: {blob.get('alg')}")
    enc, mac = _subkeys(key)
    nonce, ct = unb64u(blob["nonce"]), unb64u(blob["ct"])
    if not hmac.compare_digest(hmac.new(mac, nonce + ct, hashlib.sha256).digest(), unb64u(blob["tag"])):
        raise ValueError("печать повреждена или ключ неверный")
    return json.loads(xor(ct, _keystream(enc, nonce, len(ct))).decode())


def commitment(card, role, vote, why, salt):
    """Печать оценки: то же, что commitment() в core.js."""
    return hashlib.sha256(f"{card}|{role}|{vote}|{salt}|{why}".encode()).hexdigest()
