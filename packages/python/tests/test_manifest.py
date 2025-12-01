"""
Tests for manifest loading and validation.
"""

import json
import tempfile
import pytest
from pathlib import Path

from nebula_reconstruct.manifest import (
    load_manifest,
    verify_manifest,
    compute_merkle_root,
    ManifestError,
)


class TestLoadManifest:
    """Tests for manifest loading."""

    def test_load_valid_manifest(self, tmp_path):
        """Should load valid JSON manifest."""
        manifest_data = {
            "version": "nebula_reconstruct_v1",
            "hash_algorithm": "sha256",
            "original_size_bytes": 100,
            "rs": {"data_shards": 3, "parity_shards": 2, "total_shards": 5},
            "shards": []
        }

        manifest_file = tmp_path / "manifest.json"
        manifest_file.write_text(json.dumps(manifest_data))

        manifest = load_manifest(manifest_file)

        assert manifest["version"] == "nebula_reconstruct_v1"
        assert manifest["original_size_bytes"] == 100

    def test_load_missing_manifest(self, tmp_path):
        """Should raise error for missing file."""
        with pytest.raises(ManifestError, match="not found"):
            load_manifest(tmp_path / "nonexistent.json")

    def test_load_invalid_json(self, tmp_path):
        """Should raise error for invalid JSON."""
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("not valid json {{{")

        with pytest.raises(ManifestError, match="Invalid JSON"):
            load_manifest(bad_file)


class TestVerifyManifest:
    """Tests for manifest verification."""

    def test_verify_valid_manifest(self):
        """Should verify valid manifest structure."""
        manifest = {
            "version": "nebula_reconstruct_v1",
            "hash_algorithm": "sha256",
            "original_size_bytes": 100,
            "rs": {"data_shards": 3, "parity_shards": 2, "total_shards": 5},
            "shards": [
                {"index": 0, "hash": "abc", "path": "shard-0.bin"},
                {"index": 1, "hash": "def", "path": "shard-1.bin"},
                {"index": 2, "hash": "ghi", "path": "shard-2.bin"},
            ]
        }

        # Should not raise
        verify_manifest(manifest)

    def test_verify_missing_required_field(self):
        """Should reject manifest missing required fields."""
        manifest = {
            "version": "nebula_reconstruct_v1",
            # Missing hash_algorithm, original_size_bytes, rs, shards
        }

        with pytest.raises(ManifestError, match="Missing required field"):
            verify_manifest(manifest)

    def test_verify_unsupported_hash_algorithm(self):
        """Should reject unsupported hash algorithm."""
        manifest = {
            "version": "nebula_reconstruct_v1",
            "hash_algorithm": "md5",
            "original_size_bytes": 100,
            "rs": {"data_shards": 3, "parity_shards": 2, "total_shards": 5},
            "shards": [{"index": 0, "hash": "a", "path": "s.bin"}] * 3
        }

        with pytest.raises(ManifestError, match="Unsupported hash"):
            verify_manifest(manifest)

    def test_verify_insufficient_shards_declared(self):
        """Should reject manifest with fewer shards than k."""
        manifest = {
            "version": "nebula_reconstruct_v1",
            "hash_algorithm": "sha256",
            "original_size_bytes": 100,
            "rs": {"data_shards": 3, "parity_shards": 2, "total_shards": 5},
            "shards": [
                {"index": 0, "hash": "a", "path": "s.bin"},
                {"index": 1, "hash": "b", "path": "s.bin"},
                # Only 2 shards, need 3
            ]
        }

        with pytest.raises(ManifestError, match="Not enough shards"):
            verify_manifest(manifest)

    def test_verify_shard_hashes(self, tmp_path):
        """Should verify shard hashes when shard_dir provided."""
        import hashlib

        # Create test shard
        shard_data = b"test shard content"
        shard_hash = hashlib.sha256(shard_data).hexdigest()

        shard_file = tmp_path / "shard-0.bin"
        shard_file.write_bytes(shard_data)

        manifest = {
            "version": "nebula_reconstruct_v1",
            "hash_algorithm": "sha256",
            "original_size_bytes": len(shard_data),
            "rs": {"data_shards": 1, "parity_shards": 0, "total_shards": 1},
            "shards": [
                {"index": 0, "hash": shard_hash, "path": "shard-0.bin"}
            ]
        }

        # Should not raise
        verify_manifest(manifest, shard_dir=tmp_path)

    def test_verify_shard_hash_mismatch(self, tmp_path):
        """Should reject shard with wrong hash."""
        shard_file = tmp_path / "shard-0.bin"
        shard_file.write_bytes(b"actual content")

        manifest = {
            "version": "nebula_reconstruct_v1",
            "hash_algorithm": "sha256",
            "original_size_bytes": 100,
            "rs": {"data_shards": 1, "parity_shards": 0, "total_shards": 1},
            "shards": [
                {"index": 0, "hash": "wrong_hash_value", "path": "shard-0.bin"}
            ]
        }

        with pytest.raises(ManifestError, match="hash mismatch"):
            verify_manifest(manifest, shard_dir=tmp_path)

    def test_verify_missing_shard_file(self, tmp_path):
        """Should reject when shard file missing."""
        manifest = {
            "version": "nebula_reconstruct_v1",
            "hash_algorithm": "sha256",
            "original_size_bytes": 100,
            "rs": {"data_shards": 1, "parity_shards": 0, "total_shards": 1},
            "shards": [
                {"index": 0, "hash": "abc", "path": "missing.bin"}
            ]
        }

        with pytest.raises(ManifestError, match="missing"):
            verify_manifest(manifest, shard_dir=tmp_path)


class TestComputeMerkleRoot:
    """Tests for Merkle root computation."""

    def test_single_leaf(self):
        """Should return leaf hash for single-element tree."""
        import hashlib
        leaf = hashlib.sha256(b"data").hexdigest()

        root = compute_merkle_root([leaf])

        assert root == leaf

    def test_two_leaves(self):
        """Should compute correct root for two leaves."""
        import hashlib

        leaf1 = hashlib.sha256(b"leaf1").hexdigest()
        leaf2 = hashlib.sha256(b"leaf2").hexdigest()

        # Manual calculation
        combined = bytes.fromhex(leaf1) + bytes.fromhex(leaf2)
        expected_root = hashlib.sha256(combined).hexdigest()

        root = compute_merkle_root([leaf1, leaf2])

        assert root == expected_root

    def test_odd_number_of_leaves(self):
        """Should handle odd number of leaves (duplicate last)."""
        import hashlib

        leaves = [hashlib.sha256(str(i).encode()).hexdigest() for i in range(3)]

        # Should not raise
        root = compute_merkle_root(leaves)

        assert len(root) == 64  # SHA256 hex

    def test_empty_leaves(self):
        """Should return empty string for no leaves."""
        root = compute_merkle_root([])
        assert root == ""

    def test_deterministic(self):
        """Should produce same root for same input."""
        import hashlib
        leaves = [hashlib.sha256(str(i).encode()).hexdigest() for i in range(4)]

        root1 = compute_merkle_root(leaves)
        root2 = compute_merkle_root(leaves)

        assert root1 == root2

    def test_order_matters(self):
        """Should produce different root for different order."""
        import hashlib
        leaves = [hashlib.sha256(str(i).encode()).hexdigest() for i in range(4)]

        root1 = compute_merkle_root(leaves)
        root2 = compute_merkle_root(list(reversed(leaves)))

        assert root1 != root2
