# Nebula Reconstruction Kit

Reference toolkit for **verifiable shard reconstruction**. Designed for zero lock‑in/escrow scenarios so customers or auditors can independently rebuild encrypted data from shards and a signed manifest.

## Scope
- **Open:** Manifest schema, shard/hash verification, Reed–Solomon style k-of-n reconstruction (demo), optional AES-256-GCM decryption, Merkle root verification, reconstruction report.
- **Closed:** Placement logic, node selection, health/risk scoring, pricing models, anchoring strategy, production orchestration.

## Layout
```
nebula-reconstruction-kit/
├── schemas/manifest.schema.json   # Manifest format (versioned)
├── test-vectors/                  # Example manifest + dummy shards
├── packages/
│   ├── python/                    # Python CLI/library (nebula-reconstruct)
│   └── typescript/                # TypeScript SDK placeholder
└── README.md
```

## Manifest Essentials
- `version`: e.g., `nebula_reconstruct_v1`
- `rs`: `data_shards`, `parity_shards`, `total_shards`
- `encryption`: `algorithm` (aes-256-gcm), `iv`, optional `tag`
- `original_size_bytes`
- `shards[]`: `index`, `hash` (sha256 hex), `size_bytes`, optional `url`
- `merkle`: `root`, `algorithm`, `leaf_hashes`

## Python CLI (packages/python)
```bash
pip install .[cli]
nebula-reconstruct verify manifest.json --shard-dir test-vectors/shards
nebula-reconstruct rebuild manifest.json --shard-dir test-vectors/shards --out /tmp/recovered.bin
```

## TypeScript SDK (packages/typescript)
Skeleton SDK mirrors the Python interfaces (manifest validation + reconstruction hook). Implementation is minimal; expand as needed.

## Status
- Python: CLI + library implemented, depends on `cryptography`. Reed–Solomon step currently assumes `data_shards` sequential shards are present; swap in a production RS decoder as needed.
- TypeScript: Stubbed reconstruction interfaces for parity with Python; fill in actual RS/AES as required.

## Not Included
- No proprietary placement/orchestration logic.
- No production-grade erasure coding; replace the demo decoder with your preferred RS library.

