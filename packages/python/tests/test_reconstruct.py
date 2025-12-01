"""
Tests for file reconstruction.
"""

import json
import hashlib
import pytest
from pathlib import Path

from nebula_reconstruct import (
    encode_data,
    reconstruct_file,
    analyze_recoverability,
    load_and_verify_shards,
    ManifestError,
)


def create_test_shards(tmp_path, original_data, k=3, n=5):
    """
    Helper to create RS-encoded shards and manifest.

    Returns:
        Tuple of (manifest_dict, shards_dir)
    """
    shards, params = encode_data(original_data, k, n)

    # Create shards directory
    shards_dir = tmp_path / "shards"
    shards_dir.mkdir()

    shard_metadata = []
    leaf_hashes = []

    for i, shard_data in enumerate(shards):
        shard_path = f"shard-{i}.bin"
        (shards_dir / shard_path).write_bytes(shard_data)

        shard_hash = hashlib.sha256(shard_data).hexdigest()
        leaf_hashes.append(shard_hash)

        shard_metadata.append({
            "index": i,
            "hash": shard_hash,
            "size_bytes": len(shard_data),
            "path": shard_path
        })

    # Compute Merkle root
    from nebula_reconstruct import compute_merkle_root
    merkle_root = compute_merkle_root(leaf_hashes)

    manifest = {
        "version": "nebula_reconstruct_v1",
        "hash_algorithm": "sha256",
        "original_size_bytes": len(original_data),
        "original_hash": hashlib.sha256(original_data).hexdigest(),
        "rs": {
            "data_shards": k,
            "parity_shards": n - k,
            "total_shards": n
        },
        "shards": shard_metadata,
        "merkle": {
            "algorithm": "sha256",
            "root": merkle_root,
            "leaf_hashes": leaf_hashes
        }
    }

    return manifest, shards_dir


class TestReconstructFile:
    """Tests for reconstruct_file function."""

    def test_reconstruct_simple(self, tmp_path):
        """Should reconstruct file from all shards."""
        original = b"Hello, World! This is test data."
        manifest, shards_dir = create_test_shards(tmp_path, original)

        data, report = reconstruct_file(manifest, shards_dir)

        assert data == original
        assert report.success
        assert report.hash_verified
        assert report.shards_valid == 5
        assert report.shards_required == 3

    def test_reconstruct_with_missing_shards(self, tmp_path):
        """Should reconstruct with some shards missing."""
        original = b"Data for partial reconstruction test."
        manifest, shards_dir = create_test_shards(tmp_path, original, k=3, n=5)

        # Delete two shards (still have 3, which is enough)
        (shards_dir / "shard-1.bin").unlink()
        (shards_dir / "shard-3.bin").unlink()

        data, report = reconstruct_file(manifest, shards_dir)

        assert data == original
        assert report.success
        assert report.shards_valid == 3

    def test_reconstruct_fails_with_too_few_shards(self, tmp_path):
        """Should fail when fewer than k shards available."""
        original = b"Test data"
        manifest, shards_dir = create_test_shards(tmp_path, original, k=3, n=5)

        # Delete 3 shards, leaving only 2 (need 3)
        (shards_dir / "shard-0.bin").unlink()
        (shards_dir / "shard-2.bin").unlink()
        (shards_dir / "shard-4.bin").unlink()

        with pytest.raises(ManifestError, match="Need 3"):
            reconstruct_file(manifest, shards_dir)

    def test_reconstruct_with_corrupted_shard(self, tmp_path):
        """Should handle corrupted (hash mismatch) shards."""
        original = b"Important data that must be recovered."
        manifest, shards_dir = create_test_shards(tmp_path, original, k=3, n=5)

        # Corrupt one shard
        (shards_dir / "shard-0.bin").write_bytes(b"corrupted data")

        # Should still work if enough valid shards remain
        data, report = reconstruct_file(manifest, shards_dir)

        assert data == original
        assert report.success
        # One shard invalid (corrupted), but 4 valid shards remain
        assert report.shards_valid == 4

    def test_reconstruct_verifies_hash(self, tmp_path):
        """Should verify reconstructed data hash."""
        original = b"Hash verification test data."
        manifest, shards_dir = create_test_shards(tmp_path, original)

        data, report = reconstruct_file(manifest, shards_dir, verify_hash=True)

        assert report.hash_verified
        assert report.reconstructed_hash == manifest["original_hash"]

    def test_reconstruct_binary_data(self, tmp_path):
        """Should handle arbitrary binary data."""
        original = bytes(range(256)) * 10  # All byte values repeated
        manifest, shards_dir = create_test_shards(tmp_path, original)

        data, report = reconstruct_file(manifest, shards_dir)

        assert data == original
        assert report.success


class TestAnalyzeRecoverability:
    """Tests for analyze_recoverability function."""

    def test_analyze_all_available(self, tmp_path):
        """Should report feasible when all shards present."""
        original = b"Test data"
        manifest, shards_dir = create_test_shards(tmp_path, original)

        analysis = analyze_recoverability(manifest, shards_dir)

        assert analysis["feasible"]
        assert analysis["shards_valid"] == 5
        assert analysis["fast_path"]
        assert analysis["redundancy_margin"] == 2

    def test_analyze_partial_available(self, tmp_path):
        """Should report correct feasibility with missing shards."""
        original = b"Test data"
        manifest, shards_dir = create_test_shards(tmp_path, original, k=3, n=5)

        # Delete some shards
        (shards_dir / "shard-1.bin").unlink()
        (shards_dir / "shard-3.bin").unlink()

        analysis = analyze_recoverability(manifest, shards_dir)

        assert analysis["feasible"]
        assert analysis["shards_valid"] == 3
        assert analysis["missing_count"] == 2

    def test_analyze_not_feasible(self, tmp_path):
        """Should report not feasible when too few shards."""
        original = b"Test data"
        manifest, shards_dir = create_test_shards(tmp_path, original, k=3, n=5)

        # Delete too many shards
        (shards_dir / "shard-0.bin").unlink()
        (shards_dir / "shard-1.bin").unlink()
        (shards_dir / "shard-2.bin").unlink()

        analysis = analyze_recoverability(manifest, shards_dir)

        assert not analysis["feasible"]
        assert analysis["shards_valid"] == 2
        assert "more shard" in analysis["message"].lower()

    def test_analyze_without_shard_dir(self):
        """Should provide theoretical analysis without checking files."""
        manifest = {
            "version": "nebula_reconstruct_v1",
            "hash_algorithm": "sha256",
            "original_size_bytes": 100,
            "rs": {"data_shards": 3, "parity_shards": 2, "total_shards": 5},
            "shards": [{"index": i} for i in range(5)]
        }

        analysis = analyze_recoverability(manifest)

        assert analysis["feasible"]
        assert "note" in analysis  # Note about not checking files


class TestLoadAndVerifyShards:
    """Tests for load_and_verify_shards function."""

    def test_load_valid_shards(self, tmp_path):
        """Should load and verify valid shards."""
        original = b"Test data for shard loading."
        manifest, shards_dir = create_test_shards(tmp_path, original)

        shard_infos = load_and_verify_shards(manifest, shards_dir)

        assert len(shard_infos) == 5
        assert all(s.valid for s in shard_infos)
        assert all(s.data is not None for s in shard_infos)

    def test_load_missing_shard(self, tmp_path):
        """Should mark missing shards as invalid."""
        original = b"Test data"
        manifest, shards_dir = create_test_shards(tmp_path, original)

        # Delete one shard
        (shards_dir / "shard-2.bin").unlink()

        shard_infos = load_and_verify_shards(manifest, shards_dir)

        # Find the deleted shard
        shard_2 = next(s for s in shard_infos if s.index == 2)
        assert not shard_2.valid
        assert "not found" in shard_2.error.lower()

    def test_load_corrupted_shard(self, tmp_path):
        """Should mark corrupted shards as invalid."""
        original = b"Test data"
        manifest, shards_dir = create_test_shards(tmp_path, original)

        # Corrupt one shard
        (shards_dir / "shard-1.bin").write_bytes(b"wrong content")

        shard_infos = load_and_verify_shards(manifest, shards_dir)

        shard_1 = next(s for s in shard_infos if s.index == 1)
        assert not shard_1.valid
        assert shard_1.data is not None  # File exists but hash wrong
        assert "mismatch" in shard_1.error.lower()


class TestEndToEnd:
    """End-to-end integration tests."""

    def test_full_pipeline(self, tmp_path):
        """Should complete full encode -> save -> load -> reconstruct cycle."""
        original = b"Complete end-to-end test with real RS encoding."

        # Create shards and manifest
        manifest, shards_dir = create_test_shards(tmp_path, original, k=3, n=5)

        # Save manifest
        manifest_file = tmp_path / "manifest.json"
        manifest_file.write_text(json.dumps(manifest, indent=2))

        # Load manifest
        from nebula_reconstruct import load_manifest, verify_manifest
        loaded_manifest = load_manifest(manifest_file)
        verify_manifest(loaded_manifest, shards_dir)

        # Analyze
        analysis = analyze_recoverability(loaded_manifest, shards_dir)
        assert analysis["feasible"]

        # Reconstruct
        data, report = reconstruct_file(loaded_manifest, shards_dir)
        assert data == original
        assert report.success
        assert report.hash_verified

    def test_disaster_recovery_scenario(self, tmp_path):
        """Should recover data after losing max allowable shards."""
        original = b"Critical data that must survive disaster."
        k, n = 3, 5  # Can lose up to 2 shards

        manifest, shards_dir = create_test_shards(tmp_path, original, k=k, n=n)

        # Simulate disaster: lose maximum allowable shards (n - k = 2)
        (shards_dir / "shard-0.bin").unlink()
        (shards_dir / "shard-2.bin").unlink()

        # Should still recover
        data, report = reconstruct_file(manifest, shards_dir)

        assert data == original
        assert report.success
        assert report.shards_valid == 3  # Exactly k shards remaining
