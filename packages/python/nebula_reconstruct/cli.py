"""
Nebula Reconstruction CLI
"""

import argparse
import sys
from pathlib import Path
from typing import Optional

from .manifest import load_manifest, verify_manifest, ManifestError
from .reconstruct import reconstruct_file


def cmd_verify(args) -> int:
    try:
        manifest = load_manifest(args.manifest)
        verify_manifest(manifest, shard_dir=args.shard_dir)
        print("✅ Manifest verified")
        return 0
    except ManifestError as e:
        print(f"❌ {e}", file=sys.stderr)
        return 1


def cmd_rebuild(args) -> int:
    try:
        manifest = load_manifest(args.manifest)
        verify_manifest(manifest, shard_dir=args.shard_dir)
        key: Optional[bytes] = None
        if args.key_hex:
            key = bytes.fromhex(args.key_hex)
        data = reconstruct_file(manifest, shard_dir=args.shard_dir, key=key)
        out_path = Path(args.out)
        out_path.write_bytes(data)
        print(f"✅ Reconstructed file written to {out_path} ({len(data)} bytes)")
        return 0
    except ManifestError as e:
        print(f"❌ {e}", file=sys.stderr)
        return 1


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description="Nebula Reconstruction Kit CLI")
    parser.add_argument("--version", action="version", version="nebula-reconstruct 0.1.0")

    sub = parser.add_subparsers(dest="command")

    verify_p = sub.add_parser("verify", help="Verify manifest + shards")
    verify_p.add_argument("manifest", help="Path to manifest.json")
    verify_p.add_argument("--shard-dir", default=".", help="Directory containing shard files")
    verify_p.set_defaults(func=cmd_verify)

    rebuild_p = sub.add_parser("rebuild", help="Reconstruct file")
    rebuild_p.add_argument("manifest", help="Path to manifest.json")
    rebuild_p.add_argument("--shard-dir", default=".", help="Directory containing shard files")
    rebuild_p.add_argument("--out", required=True, help="Output file path")
    rebuild_p.add_argument("--key-hex", help="Hex-encoded AES-256-GCM key (optional)")
    rebuild_p.set_defaults(func=cmd_rebuild)

    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
