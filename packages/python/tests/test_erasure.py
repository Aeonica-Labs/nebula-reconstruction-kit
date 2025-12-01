"""
Tests for Reed-Solomon erasure coding module.
"""

import pytest
from nebula_reconstruct.erasure import (
    encode_data,
    reconstruct_data,
    analyze_reconstruction,
    RSParams,
)


class TestEncodeData:
    """Tests for RS encoding."""

    def test_encode_simple_data(self):
        """Should encode data into k data shards and n-k parity shards."""
        data = b"Hello, World! This is test data for RS encoding."
        k, n = 3, 5

        shards, params = encode_data(data, k, n)

        assert len(shards) == n
        assert params.data_shards == k
        assert params.parity_shards == n - k
        assert params.total_shards == n
        # All shards should have same size
        assert all(len(s) == params.shard_size for s in shards)

    def test_encode_small_data(self):
        """Should handle data smaller than k bytes."""
        data = b"Hi"
        k, n = 3, 5

        shards, params = encode_data(data, k, n)

        assert len(shards) == n
        assert params.shard_size >= 1

    def test_encode_exact_multiple(self):
        """Should handle data that's exact multiple of k."""
        data = b"123456"  # Exactly 6 bytes
        k, n = 3, 5

        shards, params = encode_data(data, k, n)

        assert len(shards) == n
        assert params.shard_size == 2  # 6 / 3 = 2

    def test_encode_invalid_params(self):
        """Should reject invalid k/n parameters."""
        data = b"test"

        with pytest.raises(ValueError):
            encode_data(data, k=3, n=2)  # n <= k

        with pytest.raises(ValueError):
            encode_data(data, k=0, n=3)  # k < 1


class TestReconstructData:
    """Tests for RS reconstruction."""

    def test_reconstruct_with_all_data_shards(self):
        """Should reconstruct using only data shards (fast path)."""
        original = b"Hello, World! This is test data for RS encoding."
        k, n = 3, 5

        shards, params = encode_data(original, k, n)

        # Use only first k shards (data shards)
        result = reconstruct_data(
            shards=shards[:k],
            shard_indices=list(range(k)),
            params=params,
            original_size=len(original)
        )

        assert result.success
        assert result.data == original
        assert result.shards_used == k
        assert result.corrected_errors == 0

    def test_reconstruct_with_parity_shards(self):
        """Should reconstruct using mix of data and parity shards."""
        original = b"Hello, World! This is test data for RS encoding."
        k, n = 3, 5

        shards, params = encode_data(original, k, n)

        # Use shards 0, 2, 4 (skipping 1 and 3)
        selected_indices = [0, 2, 4]
        selected_shards = [shards[i] for i in selected_indices]

        result = reconstruct_data(
            shards=selected_shards,
            shard_indices=selected_indices,
            params=params,
            original_size=len(original)
        )

        assert result.success
        assert result.data == original

    def test_reconstruct_with_only_parity(self):
        """Should reconstruct using only parity + some data shards."""
        original = b"Test data for reconstruction."
        k, n = 2, 4

        shards, params = encode_data(original, k, n)

        # Use shards 1, 2, 3 (one data, two parity)
        selected_indices = [1, 2, 3]
        selected_shards = [shards[i] for i in selected_indices]

        result = reconstruct_data(
            shards=selected_shards,
            shard_indices=selected_indices,
            params=params,
            original_size=len(original)
        )

        assert result.success
        assert result.data == original

    def test_reconstruct_insufficient_shards(self):
        """Should fail when fewer than k shards available."""
        original = b"Test data"
        k, n = 3, 5

        shards, params = encode_data(original, k, n)

        # Only provide 2 shards when 3 needed
        result = reconstruct_data(
            shards=shards[:2],
            shard_indices=[0, 1],
            params=params,
            original_size=len(original)
        )

        assert not result.success
        assert result.data is None
        assert "Need 3 shards" in result.error

    def test_reconstruct_preserves_original_size(self):
        """Should trim padding to original size."""
        original = b"Odd length data"  # 15 bytes, won't divide evenly by k=4
        k, n = 4, 6

        shards, params = encode_data(original, k, n)

        result = reconstruct_data(
            shards=shards[:k],
            shard_indices=list(range(k)),
            params=params,
            original_size=len(original)
        )

        assert result.success
        assert result.data == original
        assert len(result.data) == len(original)


class TestAnalyzeReconstruction:
    """Tests for reconstruction analysis."""

    def test_analyze_feasible(self):
        """Should report feasible when enough shards available."""
        result = analyze_reconstruction(
            available_indices=[0, 2, 4],
            k=3,
            n=5
        )

        assert result["feasible"]
        assert result["available_shards"] == 3
        assert result["required_shards"] == 3
        assert result["redundancy_margin"] == 0
        assert "possible" in result["message"].lower()

    def test_analyze_with_redundancy(self):
        """Should report redundancy margin."""
        result = analyze_reconstruction(
            available_indices=[0, 1, 2, 3, 4],
            k=3,
            n=5
        )

        assert result["feasible"]
        assert result["redundancy_margin"] == 2
        assert result["fast_path"]  # All data shards present

    def test_analyze_not_feasible(self):
        """Should report not feasible when insufficient shards."""
        result = analyze_reconstruction(
            available_indices=[0, 1],
            k=3,
            n=5
        )

        assert not result["feasible"]
        assert "more shard" in result["message"].lower()

    def test_analyze_fast_path_detection(self):
        """Should detect fast path when all data shards present."""
        # All data shards present
        result1 = analyze_reconstruction([0, 1, 2], k=3, n=5)
        assert result1["fast_path"]

        # Missing one data shard (but still feasible)
        result2 = analyze_reconstruction([0, 2, 3], k=3, n=5)
        assert not result2["fast_path"]
        assert result2["feasible"]


class TestRoundTrip:
    """End-to-end tests for encode -> reconstruct cycle."""

    @pytest.mark.parametrize("k,n", [(2, 3), (3, 5), (4, 7), (2, 5)])
    def test_various_k_n_combinations(self, k, n):
        """Should work with various k/n combinations."""
        original = b"Test data for various RS parameters"

        shards, params = encode_data(original, k, n)

        # Reconstruct with exactly k shards
        result = reconstruct_data(
            shards=shards[:k],
            shard_indices=list(range(k)),
            params=params,
            original_size=len(original)
        )

        assert result.success
        assert result.data == original

    @pytest.mark.parametrize("size", [1, 10, 100, 1000, 10000])
    def test_various_data_sizes(self, size):
        """Should handle various data sizes."""
        original = bytes(range(256)) * (size // 256 + 1)
        original = original[:size]
        k, n = 3, 5

        shards, params = encode_data(original, k, n)

        result = reconstruct_data(
            shards=shards[:k],
            shard_indices=list(range(k)),
            params=params,
            original_size=len(original)
        )

        assert result.success
        assert result.data == original

    def test_binary_data(self):
        """Should handle arbitrary binary data."""
        original = bytes(range(256))  # All byte values
        k, n = 4, 6

        shards, params = encode_data(original, k, n)

        result = reconstruct_data(
            shards=shards[:k],
            shard_indices=list(range(k)),
            params=params,
            original_size=len(original)
        )

        assert result.success
        assert result.data == original
