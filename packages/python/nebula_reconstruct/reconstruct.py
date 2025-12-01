"""
File Reconstruction for Nebula Reconstruction Kit.

Reconstructs original files from shards using:
- Reed-Solomon erasure coding (any k-of-n shards)
- Optional AES-256-GCM decryption
- Hash verification

This module provides the core reconstruction logic that allows
data recovery without depending on Nebula infrastructure.
"""

import hashlib
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .manifest import ManifestError
from .erasure import RSParams, reconstruct_data, analyze_reconstruction, ReconstructionResult


@dataclass
class ShardInfo:
    """Information about a single shard."""
    index: int
    path: str
    expected_hash: str
    size: int
    data: Optional[bytes] = None
    actual_hash: Optional[str] = None
    valid: bool = False
    error: Optional[str] = None


@dataclass
class ReconstructionReport:
    """Detailed report of reconstruction attempt."""
    success: bool
    feasible: bool
    original_size: int
    reconstructed_size: int
    original_hash: Optional[str]
    reconstructed_hash: Optional[str]
    hash_verified: bool
    decrypted: bool
    shards_required: int
    shards_available: int
    shards_valid: int
    shard_details: List[ShardInfo] = field(default_factory=list)
    rs_errors_corrected: int = 0
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "success": self.success,
            "feasible": self.feasible,
            "original_size": self.original_size,
            "reconstructed_size": self.reconstructed_size,
            "original_hash": self.original_hash,
            "reconstructed_hash": self.reconstructed_hash,
            "hash_verified": self.hash_verified,
            "decrypted": self.decrypted,
            "shards_required": self.shards_required,
            "shards_available": self.shards_available,
            "shards_valid": self.shards_valid,
            "rs_errors_corrected": self.rs_errors_corrected,
            "shard_details": [
                {
                    "index": s.index,
                    "path": s.path,
                    "valid": s.valid,
                    "error": s.error
                }
                for s in self.shard_details
            ],
            "error": self.error
        }


def load_and_verify_shards(
    manifest: Dict[str, Any],
    shard_dir: Path
) -> List[ShardInfo]:
    """
    Load shards from disk and verify their hashes.

    Args:
        manifest: Reconstruction manifest
        shard_dir: Directory containing shard files

    Returns:
        List of ShardInfo with loaded data and validation status
    """
    shard_infos = []

    for shard in manifest["shards"]:
        info = ShardInfo(
            index=shard["index"],
            path=shard["path"],
            expected_hash=shard["hash"],
            size=shard.get("size_bytes", 0)
        )

        shard_path = shard_dir / shard["path"]

        try:
            if not shard_path.exists():
                info.error = f"File not found: {shard_path}"
                shard_infos.append(info)
                continue

            data = shard_path.read_bytes()
            info.data = data
            info.actual_hash = hashlib.sha256(data).hexdigest()

            if info.actual_hash == info.expected_hash:
                info.valid = True
            else:
                info.error = f"Hash mismatch: expected {info.expected_hash[:16]}..., got {info.actual_hash[:16]}..."

        except Exception as e:
            info.error = str(e)

        shard_infos.append(info)

    return shard_infos


def analyze_recoverability(
    manifest: Dict[str, Any],
    shard_dir: Optional[str | Path] = None
) -> Dict[str, Any]:
    """
    Analyze whether reconstruction is possible without actually reconstructing.

    Args:
        manifest: Reconstruction manifest
        shard_dir: Optional directory to verify shard availability

    Returns:
        Analysis dict with feasibility assessment
    """
    rs = manifest["rs"]
    k = rs["data_shards"]
    n = rs["total_shards"]

    result = {
        "k": k,
        "n": n,
        "original_size": manifest["original_size_bytes"],
        "original_hash": manifest.get("original_hash"),
        "shards_declared": len(manifest["shards"]),
    }

    if shard_dir:
        shard_dir = Path(shard_dir)
        shard_infos = load_and_verify_shards(manifest, shard_dir)
        valid_indices = [s.index for s in shard_infos if s.valid]

        analysis = analyze_reconstruction(valid_indices, k, n)
        result.update({
            "shards_found": len([s for s in shard_infos if s.data is not None]),
            "shards_valid": len(valid_indices),
            "valid_indices": valid_indices,
            "feasible": analysis["feasible"],
            "fast_path": analysis["fast_path"],
            "missing_count": analysis["missing_count"],
            "redundancy_margin": analysis["redundancy_margin"],
            "message": analysis["message"],
            "shard_status": [
                {"index": s.index, "valid": s.valid, "error": s.error}
                for s in shard_infos
            ]
        })
    else:
        # Without shard_dir, assume all declared shards are available
        declared_indices = [s["index"] for s in manifest["shards"]]
        analysis = analyze_reconstruction(declared_indices, k, n)
        result.update({
            "feasible": analysis["feasible"],
            "message": analysis["message"],
            "note": "Actual shard availability not verified (no shard_dir provided)"
        })

    return result


def reconstruct_file(
    manifest: Dict[str, Any],
    shard_dir: str | Path,
    key: Optional[bytes] = None,
    verify_hash: bool = True
) -> Tuple[bytes, ReconstructionReport]:
    """
    Reconstruct original file from shards.

    Args:
        manifest: Reconstruction manifest
        shard_dir: Directory containing shard files
        key: Optional AES-256-GCM key for decryption
        verify_hash: Whether to verify reconstructed data hash

    Returns:
        Tuple of (reconstructed data, detailed report)

    Raises:
        ManifestError: If reconstruction fails
    """
    shard_dir = Path(shard_dir)
    rs = manifest["rs"]
    k = rs["data_shards"]
    n = rs["total_shards"]
    original_size = manifest["original_size_bytes"]
    original_hash = manifest.get("original_hash")

    # Load and verify shards
    shard_infos = load_and_verify_shards(manifest, shard_dir)
    valid_shards = [s for s in shard_infos if s.valid]

    report = ReconstructionReport(
        success=False,
        feasible=len(valid_shards) >= k,
        original_size=original_size,
        reconstructed_size=0,
        original_hash=original_hash,
        reconstructed_hash=None,
        hash_verified=False,
        decrypted=False,
        shards_required=k,
        shards_available=len([s for s in shard_infos if s.data is not None]),
        shards_valid=len(valid_shards),
        shard_details=shard_infos
    )

    if not report.feasible:
        report.error = f"Need {k} valid shards, only {len(valid_shards)} available"
        raise ManifestError(report.error)

    # Determine shard size from first valid shard
    shard_size = len(valid_shards[0].data) if valid_shards else 0

    # Build RS params
    params = RSParams(
        data_shards=k,
        parity_shards=n - k,
        total_shards=n,
        shard_size=shard_size
    )

    # Prepare shards for reconstruction
    shard_data_list = [s.data for s in valid_shards]
    shard_indices = [s.index for s in valid_shards]

    # Reconstruct
    rs_result = reconstruct_data(
        shards=shard_data_list,
        shard_indices=shard_indices,
        params=params,
        original_size=original_size
    )

    if not rs_result.success:
        report.error = rs_result.error
        raise ManifestError(f"RS reconstruction failed: {rs_result.error}")

    reconstructed = rs_result.data
    report.rs_errors_corrected = rs_result.corrected_errors

    # Handle encryption
    enc = manifest.get("encryption")
    if enc:
        if enc.get("algorithm") != "aes-256-gcm":
            report.error = f"Unsupported encryption: {enc.get('algorithm')}"
            raise ManifestError(report.error)

        if not key:
            report.error = "Decryption key required but not provided"
            raise ManifestError(report.error)

        iv_hex = enc.get("iv")
        tag_hex = enc.get("tag")

        if not iv_hex:
            report.error = "Missing IV for AES-GCM"
            raise ManifestError(report.error)

        try:
            aesgcm = AESGCM(key)
            iv = bytes.fromhex(iv_hex)

            # If tag is separate, append it to ciphertext
            if tag_hex:
                ciphertext_with_tag = reconstructed + bytes.fromhex(tag_hex)
            else:
                ciphertext_with_tag = reconstructed

            reconstructed = aesgcm.decrypt(iv, ciphertext_with_tag, None)
            report.decrypted = True
        except Exception as e:
            report.error = f"Decryption failed: {e}"
            raise ManifestError(report.error)

    report.reconstructed_size = len(reconstructed)
    report.reconstructed_hash = hashlib.sha256(reconstructed).hexdigest()

    # Verify hash if requested and original hash available
    if verify_hash and original_hash:
        report.hash_verified = report.reconstructed_hash == original_hash
        if not report.hash_verified:
            report.error = f"Hash mismatch: expected {original_hash[:16]}..., got {report.reconstructed_hash[:16]}..."
            raise ManifestError(report.error)

    report.success = True
    return reconstructed, report
