# Nebula Reconstruction Kit (Python)

Reference CLI + library for verifying and reconstructing shards using a Nebula reconstruction manifest. Intended for escrow/zero-lock-in scenarios.

## Install (local path)
```bash
pip install -e .  # from packages/python
```

## CLI
```bash
# Verify manifest + shards
nebula-reconstruct verify ../../test-vectors/manifest.json --shard-dir ../../test-vectors/shards

# Rebuild file (no encryption in the demo vector)
nebula-reconstruct rebuild ../../test-vectors/manifest.json --shard-dir ../../test-vectors/shards --out /tmp/recovered.bin
```

## Library
```python
from nebula_reconstruct import load_manifest, verify_manifest, reconstruct_file
manifest = load_manifest("manifest.json")
verify_manifest(manifest, shard_dir="shards")
data = reconstruct_file(manifest, shard_dir="shards", key=None)
```

## Notes
- Uses SHA-256 for shard/Merkle verification.
- Uses AES-256-GCM if `encryption` is present in the manifest (demo vectors are unencrypted).
- RS step currently assumes `data_shards` consecutive shards are present; swap in your preferred Reed–Solomon decoder for production.
- No proprietary placement/orchestration logic is included.

## License
Apache-2.0
