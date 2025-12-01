# Nebula Reconstruction Kit

**Zero lock-in toolkit for verifiable data reconstruction from distributed shards.**

This kit answers the critical question: **"Can I actually recover my data?"**

> **Relationship to [`nebula-proof-kit`](https://github.com/Aeonica-Labs/nebula-proof-kit):**
> - `nebula-proof-kit` answers: *"Is this cryptographic proof valid?"* (Merkle proofs, signatures, anchoring)
> - `nebula-reconstruction-kit` answers: *"Can I reconstruct the original data?"* (Reed-Solomon decoding, shard verification, decryption)
>
> Use both together for complete verifiable storage: proofs ensure integrity, reconstruction ensures recoverability.

## Features

- **Real Reed-Solomon erasure coding** - k-of-n reconstruction using `reedsolo` library
- **Shard verification** - SHA-256 hash verification for each shard
- **Merkle tree validation** - Verify manifest integrity against Merkle root
- **AES-256-GCM decryption** - Decrypt reconstructed data with proper auth tag handling
- **Recoverability analysis** - Determine if reconstruction is feasible before attempting
- **Detailed reporting** - Comprehensive reports on reconstruction attempts

## Quick Start

### Python

```bash
cd packages/python
pip install -e .

# Analyze recoverability
python -c "
from nebula_reconstruct import load_manifest, analyze_recoverability
manifest = load_manifest('../../test-vectors/manifest.json')
analysis = analyze_recoverability(manifest, '../../test-vectors')
print(f'Feasible: {analysis[\"feasible\"]}, Valid shards: {analysis[\"shards_valid\"]}')
"

# Full reconstruction
python -c "
from nebula_reconstruct import load_manifest, reconstruct_file
manifest = load_manifest('../../test-vectors/manifest.json')
data, report = reconstruct_file(manifest, '../../test-vectors')
print(f'Recovered {len(data)} bytes, hash verified: {report.hash_verified}')
"
```

### TypeScript

```bash
cd packages/typescript
npm install
npm run build

# Use in your code
import { loadManifest, reconstructFile, analyzeRecoverability } from '@nebula/reconstruct-kit';

const manifest = await loadManifest('./manifest.json');
const analysis = await analyzeRecoverability(manifest, './shards');

if (analysis.feasible) {
  const { data, report } = await reconstructFile(manifest, './shards');
  console.log(`Recovered ${data.length} bytes, verified: ${report.hashVerified}`);
}
```

## Layout

```
nebula-reconstruction-kit/
├── schemas/manifest.schema.json   # Manifest JSON schema
├── test-vectors/                  # Example manifest + test shards
├── packages/
│   ├── python/                    # Python SDK with real RS encoding
│   │   ├── nebula_reconstruct/
│   │   │   ├── manifest.py        # Manifest loading/verification
│   │   │   ├── erasure.py         # Reed-Solomon encoding/decoding
│   │   │   └── reconstruct.py     # Full reconstruction pipeline
│   │   └── tests/                 # 54 comprehensive tests
│   └── typescript/                # TypeScript SDK
│       └── src/
│           ├── index.ts           # Full SDK implementation
│           └── index.test.ts      # 17 tests
└── README.md
```

## Manifest Schema

```json
{
  "version": "nebula_reconstruct_v1",
  "hash_algorithm": "sha256",
  "original_size_bytes": 1234,
  "original_hash": "abc123...",
  "rs": {
    "data_shards": 3,
    "parity_shards": 2,
    "total_shards": 5
  },
  "shards": [
    { "index": 0, "hash": "...", "size_bytes": 100, "path": "shards/shard-0.bin" }
  ],
  "merkle": {
    "algorithm": "sha256",
    "root": "...",
    "leaf_hashes": ["...", "..."]
  },
  "encryption": {
    "algorithm": "aes-256-gcm",
    "iv": "...",
    "tag": "..."
  }
}
```

## Reed-Solomon Parameters

The kit uses standard Reed-Solomon erasure coding:

- **k** = data shards (minimum needed for reconstruction)
- **n** = total shards (data + parity)
- **Fault tolerance** = n - k shards can be lost

Example: With k=3, n=5, you can lose any 2 shards and still recover the original data.

## API Reference

### Python

```python
from nebula_reconstruct import (
    load_manifest,           # Load and parse manifest JSON
    verify_manifest,         # Verify manifest structure and shard hashes
    encode_data,             # Encode data into RS shards
    reconstruct_file,        # Full reconstruction pipeline
    analyze_recoverability,  # Check if reconstruction is possible
    load_and_verify_shards,  # Load shards and verify their hashes
    compute_merkle_root,     # Compute Merkle root from leaf hashes
)
```

### TypeScript

```typescript
import {
  loadManifest,           // Load and parse manifest JSON
  verifyManifest,         // Verify manifest structure and shard hashes
  reconstructFile,        // Full reconstruction pipeline
  analyzeRecoverability,  // Check if reconstruction is possible
  analyzeReconstruction,  // Analyze reconstruction feasibility from indices
  loadAndVerifyShards,    // Load shards and verify their hashes
  computeMerkleRoot,      // Compute Merkle root from leaf hashes
  ManifestError,          // Error class for manifest issues
} from '@nebula/reconstruct-kit';
```

## Testing

```bash
# Python (54 tests)
cd packages/python
pip install -e ".[dev]"
pytest -v

# TypeScript (17 tests)
cd packages/typescript
npm install
npm test
```

## What's Included vs Not Included

### Included (Open Source)
- Manifest schema and validation
- SHA-256 shard hash verification
- Real Reed-Solomon encoding/decoding (GF(2^8))
- AES-256-GCM decryption
- Merkle tree verification
- Recoverability analysis
- Comprehensive test suites

### Not Included (Proprietary)
- Shard placement/distribution logic
- Node selection algorithms
- Health/risk scoring
- Pricing models
- Anchoring strategy details
- Production orchestration

## License

MIT
