"""
Reconstruction helpers (demo implementation).

Notes:
- For production, swap the simple concatenation strategy with a true Reed–Solomon decoder.
- AES-256-GCM decryption is applied if an encryption block exists in the manifest.
"""

import hashlib
from pathlib import Path
from typing import Dict, Any, List, Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .manifest import ManifestError


def _load_shard_data(shards: List[Dict[str, Any]], shard_dir: Path) -> List[bytes]:
    data = []
    for shard in shards:
        shard_path = shard_dir / shard["path"]
        if not shard_path.exists():
            raise ManifestError(f"Shard file missing: {shard_path}")
        chunk = shard_path.read_bytes()
        digest = hashlib.sha256(chunk).hexdigest()
        if digest != shard["hash"]:
            raise ManifestError(f"Shard hash mismatch: {shard_path}")
        data.append(chunk)
    return data


def reconstruct_file(manifest: Dict[str, Any], shard_dir: str | Path, key: Optional[bytes] = None) -> bytes:
    shard_dir = Path(shard_dir)
    shards = manifest["shards"]
    rs = manifest["rs"]
    k = rs["data_shards"]

    # Simple strategy: require at least k shards, take the first k in order
    available = sorted(shards, key=lambda s: s["index"])
    if len(available) < k:
        raise ManifestError(f"Need {k} shards, found {len(available)}")

    shard_data = _load_shard_data(available[:k], shard_dir)

    # Demo reconstruction: concatenate first k shards
    reconstructed = b"".join(shard_data)[: manifest["original_size_bytes"]]

    # Optional AES-GCM decrypt
    enc = manifest.get("encryption")
    if enc:
        if enc.get("algorithm") != "aes-256-gcm":
            raise ManifestError(f"Unsupported encryption algorithm: {enc.get('algorithm')}")
        if not key:
            raise ManifestError("Key required for decryption")
        iv_hex = enc.get("iv")
        tag_hex = enc.get("tag")
        if not iv_hex or not tag_hex:
            raise ManifestError("Missing IV or tag for AES-GCM")
        aesgcm = AESGCM(key)
        reconstructed = aesgcm.decrypt(bytes.fromhex(iv_hex), reconstructed + bytes.fromhex(tag_hex), None)

    return reconstructed
