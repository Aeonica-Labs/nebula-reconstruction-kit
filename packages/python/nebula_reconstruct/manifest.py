"""
Manifest loading and validation for Nebula Reconstruction Kit.
"""

import json
import hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional


class ManifestError(Exception):
    """Raised when a manifest is invalid or fails verification."""


def load_manifest(path: str | Path) -> Dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise ManifestError(f"Manifest not found: {path}")
    try:
        with p.open("r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        raise ManifestError(f"Invalid JSON: {e}") from e


def verify_manifest(manifest: Dict[str, Any], shard_dir: Optional[str | Path] = None) -> None:
    """Lightweight structural checks + optional shard hash verification."""
    required_top = ["version", "hash_algorithm", "original_size_bytes", "rs", "shards"]
    for key in required_top:
        if key not in manifest:
            raise ManifestError(f"Missing required field: {key}")

    if manifest["hash_algorithm"] != "sha256":
        raise ManifestError(f"Unsupported hash algorithm: {manifest['hash_algorithm']}")

    rs = manifest["rs"]
    for key in ["data_shards", "parity_shards", "total_shards"]:
        if key not in rs:
            raise ManifestError(f"rs.{key} missing")

    shards: List[Dict[str, Any]] = manifest["shards"]
    if len(shards) < rs["data_shards"]:
        raise ManifestError("Not enough shards to reconstruct (less than data_shards)")

    # Optional shard hash verification if shard_dir provided
    if shard_dir:
        shard_base = Path(shard_dir)
        for shard in shards:
            if "path" not in shard or "hash" not in shard:
                raise ManifestError("Shard missing path or hash")
            shard_path = shard_base / shard["path"]
            if not shard_path.exists():
                raise ManifestError(f"Shard file missing: {shard_path}")
            data = shard_path.read_bytes()
            digest = hashlib.sha256(data).hexdigest()
            if digest != shard["hash"]:
                raise ManifestError(f"Shard hash mismatch for {shard_path}")

    # Merkle check (optional)
    merkle = manifest.get("merkle")
    if merkle and merkle.get("root"):
        computed_root = compute_merkle_root(merkle.get("leaf_hashes", []))
        if computed_root != merkle["root"]:
            raise ManifestError("Merkle root mismatch")


def compute_merkle_root(leaves: List[str]) -> str:
    """Compute a simple binary Merkle root from hex leaf hashes."""
    if not leaves:
        return ""
    layer = [bytes.fromhex(h) for h in leaves]
    while len(layer) > 1:
        if len(layer) % 2 == 1:
            layer.append(layer[-1])
        next_layer = []
        for i in range(0, len(layer), 2):
            next_layer.append(hashlib.sha256(layer[i] + layer[i + 1]).digest())
        layer = next_layer
    return layer[0].hex()
