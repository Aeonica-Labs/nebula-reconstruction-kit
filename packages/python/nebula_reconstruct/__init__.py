"""
Nebula Reconstruction Kit - Python SDK

Zero-lock-in toolkit for verifying and reconstructing data from Nebula shards.

Where `nebula-proof-kit` answers "Is this proof cryptographically valid?",
this kit answers "Can we actually recover the data?"

For the people. With love and freedom.
"""

from .manifest import (
    load_manifest,
    verify_manifest,
    compute_merkle_root,
    ManifestError,
)
from .reconstruct import (
    reconstruct_file,
    analyze_recoverability,
    load_and_verify_shards,
    ReconstructionReport,
    ShardInfo,
)
from .erasure import (
    encode_data,
    reconstruct_data,
    analyze_reconstruction,
    RSParams,
    ReconstructionResult,
)

__version__ = "0.1.0"
__all__ = [
    # Manifest
    "load_manifest",
    "verify_manifest",
    "compute_merkle_root",
    "ManifestError",
    # Reconstruction
    "reconstruct_file",
    "analyze_recoverability",
    "load_and_verify_shards",
    "ReconstructionReport",
    "ShardInfo",
    # Erasure coding
    "encode_data",
    "reconstruct_data",
    "analyze_reconstruction",
    "RSParams",
    "ReconstructionResult",
]
