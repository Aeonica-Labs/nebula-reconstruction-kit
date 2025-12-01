"""
Reed-Solomon Erasure Coding for Nebula Reconstruction Kit.

Implements systematic RS encoding where:
- First k shards are data shards (original data split)
- Next (n-k) shards are parity shards (redundancy)
- Any k shards can reconstruct the original data

Uses reedsolo library for GF(2^8) Reed-Solomon operations.
"""

from typing import List, Tuple, Optional
from dataclasses import dataclass
import math

from reedsolo import RSCodec, ReedSolomonError


@dataclass
class RSParams:
    """Reed-Solomon encoding parameters."""
    data_shards: int      # k - number of data shards
    parity_shards: int    # n-k - number of parity shards
    total_shards: int     # n - total shards
    shard_size: int       # Size of each shard in bytes

    @property
    def can_recover_from(self) -> int:
        """Minimum shards needed to reconstruct."""
        return self.data_shards


@dataclass
class ReconstructionResult:
    """Result of reconstruction attempt."""
    success: bool
    data: Optional[bytes]
    original_size: int
    shards_used: int
    shards_available: int
    shards_required: int
    error: Optional[str] = None
    corrected_errors: int = 0


def encode_data(data: bytes, k: int, n: int) -> Tuple[List[bytes], RSParams]:
    """
    Encode data into n shards using Reed-Solomon erasure coding.

    Args:
        data: Original data to encode
        k: Number of data shards (minimum required for reconstruction)
        n: Total number of shards (k data + n-k parity)

    Returns:
        Tuple of (list of shard bytes, RSParams)

    The encoding works as follows:
    1. Pad data to be divisible by k
    2. Split into k equal data shards
    3. Generate n-k parity shards using RS coding
    """
    if n <= k:
        raise ValueError(f"Total shards (n={n}) must be greater than data shards (k={k})")
    if k < 1:
        raise ValueError("Must have at least 1 data shard")

    parity_count = n - k

    # Pad data to be divisible by k
    original_size = len(data)
    padded_size = math.ceil(original_size / k) * k
    padded_data = data.ljust(padded_size, b'\x00')

    shard_size = padded_size // k

    # Split into k data shards
    data_shards = [
        padded_data[i * shard_size:(i + 1) * shard_size]
        for i in range(k)
    ]

    # Generate parity shards using RS coding
    # We encode each byte position across all shards
    rs = RSCodec(parity_count)

    parity_shards = [bytearray(shard_size) for _ in range(parity_count)]

    for byte_pos in range(shard_size):
        # Get byte at this position from each data shard
        data_bytes = bytes([shard[byte_pos] for shard in data_shards])

        # RS encode to get parity bytes
        encoded = rs.encode(data_bytes)
        parity_bytes = encoded[k:]  # Last parity_count bytes are parity

        # Store parity bytes in parity shards
        for parity_idx, parity_byte in enumerate(parity_bytes):
            parity_shards[parity_idx][byte_pos] = parity_byte

    all_shards = data_shards + [bytes(ps) for ps in parity_shards]

    params = RSParams(
        data_shards=k,
        parity_shards=parity_count,
        total_shards=n,
        shard_size=shard_size
    )

    return all_shards, params


def reconstruct_data(
    shards: List[Optional[bytes]],
    shard_indices: List[int],
    params: RSParams,
    original_size: int
) -> ReconstructionResult:
    """
    Reconstruct original data from available shards.

    Args:
        shards: List of available shard data (same order as shard_indices)
        shard_indices: Index of each shard (0 to n-1)
        params: RS encoding parameters
        original_size: Original data size before padding

    Returns:
        ReconstructionResult with success status and recovered data
    """
    k = params.data_shards
    n = params.total_shards
    parity_count = n - k
    shard_size = params.shard_size

    available_count = len([s for s in shards if s is not None])

    if available_count < k:
        return ReconstructionResult(
            success=False,
            data=None,
            original_size=original_size,
            shards_used=0,
            shards_available=available_count,
            shards_required=k,
            error=f"Need {k} shards, only {available_count} available"
        )

    # Build shard map: index -> data
    shard_map = {}
    for idx, shard_data in zip(shard_indices, shards):
        if shard_data is not None:
            shard_map[idx] = shard_data

    # If we have all k data shards (indices 0 to k-1), just concatenate
    have_all_data_shards = all(i in shard_map for i in range(k))

    if have_all_data_shards:
        reconstructed = b''.join(shard_map[i] for i in range(k))
        return ReconstructionResult(
            success=True,
            data=reconstructed[:original_size],
            original_size=original_size,
            shards_used=k,
            shards_available=available_count,
            shards_required=k,
            corrected_errors=0
        )

    # Need to use RS decoding to recover missing data shards
    rs = RSCodec(parity_count)

    # Reconstruct byte by byte across shards
    reconstructed_data_shards = [bytearray(shard_size) for _ in range(k)]
    corrected_count = 0

    try:
        for byte_pos in range(shard_size):
            # Build erasure-marked codeword
            # We need k + parity_count bytes, with erasures marked
            codeword = bytearray(n)
            erasure_positions = []

            for shard_idx in range(n):
                if shard_idx in shard_map:
                    codeword[shard_idx] = shard_map[shard_idx][byte_pos]
                else:
                    codeword[shard_idx] = 0  # Placeholder
                    erasure_positions.append(shard_idx)

            # Decode with erasure positions
            try:
                decoded, _, errata_pos = rs.decode(bytes(codeword), erase_pos=erasure_positions)
                if errata_pos:
                    corrected_count += len(errata_pos)
            except ReedSolomonError as e:
                return ReconstructionResult(
                    success=False,
                    data=None,
                    original_size=original_size,
                    shards_used=0,
                    shards_available=available_count,
                    shards_required=k,
                    error=f"RS decode failed at byte {byte_pos}: {e}"
                )

            # Store decoded data bytes
            for i in range(k):
                reconstructed_data_shards[i][byte_pos] = decoded[i]

        # Concatenate reconstructed data shards
        reconstructed = b''.join(bytes(shard) for shard in reconstructed_data_shards)

        return ReconstructionResult(
            success=True,
            data=reconstructed[:original_size],
            original_size=original_size,
            shards_used=available_count,
            shards_available=available_count,
            shards_required=k,
            corrected_errors=corrected_count
        )

    except Exception as e:
        return ReconstructionResult(
            success=False,
            data=None,
            original_size=original_size,
            shards_used=0,
            shards_available=available_count,
            shards_required=k,
            error=str(e)
        )


def analyze_reconstruction(
    available_indices: List[int],
    k: int,
    n: int
) -> dict:
    """
    Analyze whether reconstruction is feasible without actually reconstructing.

    Args:
        available_indices: List of available shard indices
        k: Data shards required
        n: Total shards

    Returns:
        Analysis dict with feasibility and details
    """
    available_count = len(available_indices)
    missing_indices = [i for i in range(n) if i not in available_indices]

    # Check if we have all data shards (fast path)
    data_shard_indices = set(range(k))
    have_all_data = data_shard_indices.issubset(set(available_indices))

    return {
        "feasible": available_count >= k,
        "available_shards": available_count,
        "required_shards": k,
        "total_shards": n,
        "missing_shards": missing_indices,
        "missing_count": len(missing_indices),
        "redundancy_margin": available_count - k,
        "fast_path": have_all_data,  # True if no RS decoding needed
        "message": (
            "Reconstruction possible" if available_count >= k
            else f"Need {k - available_count} more shard(s)"
        )
    }
