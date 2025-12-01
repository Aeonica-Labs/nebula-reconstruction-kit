import { createHash } from "crypto";
import { promises as fs } from "fs";
import { join } from "path";

export interface ReconstructionManifest {
  version: string;
  hash_algorithm: "sha256";
  original_size_bytes: number;
  rs: {
    data_shards: number;
    parity_shards: number;
    total_shards: number;
  };
  shards: Array<{
    index: number;
    hash: string;
    size_bytes: number;
    path?: string;
    url?: string;
  }>;
  merkle?: {
    algorithm: "sha256";
    root: string;
    leaf_hashes: string[];
  };
  encryption?: {
    algorithm: "aes-256-gcm";
    iv: string;
    tag?: string;
    key_hint?: string;
  };
}

export class ManifestError extends Error {}

export async function loadManifest(path: string): Promise<ReconstructionManifest> {
  const raw = await fs.readFile(path, "utf-8");
  const manifest = JSON.parse(raw);
  return manifest;
}

export async function verifyManifest(manifest: ReconstructionManifest, shardDir?: string): Promise<void> {
  if (manifest.hash_algorithm !== "sha256") {
    throw new ManifestError(`Unsupported hash algorithm: ${manifest.hash_algorithm}`);
  }
  if (manifest.shards.length < manifest.rs.data_shards) {
    throw new ManifestError("Not enough shards to reconstruct");
  }

  if (shardDir) {
    for (const shard of manifest.shards) {
      if (!shard.path) throw new ManifestError("Shard missing path");
      const data = await fs.readFile(join(shardDir, shard.path));
      const digest = createHash("sha256").update(data).digest("hex");
      if (digest !== shard.hash) throw new ManifestError(`Shard hash mismatch: ${shard.path}`);
    }
  }

  if (manifest.merkle?.root) {
    const root = computeMerkleRoot(manifest.merkle.leaf_hashes || []);
    if (root !== manifest.merkle.root) throw new ManifestError("Merkle root mismatch");
  }
}

export function computeMerkleRoot(leaves: string[]): string {
  if (!leaves.length) return "";
  let layer: Buffer[] = leaves.map((h) => Buffer.from(h, "hex"));
  while (layer.length > 1) {
    if (layer.length % 2 === 1) layer.push(layer[layer.length - 1]);
    const next: Buffer[] = [];
    for (let i = 0; i < layer.length; i += 2) {
      const combined = Buffer.concat([layer[i], layer[i + 1]]);
      next.push(createHash("sha256").update(combined).digest() as Buffer);
    }
    layer = next;
  }
  return layer[0].toString("hex");
}

export async function reconstructFile(
  manifest: ReconstructionManifest,
  shardDir: string,
  key?: Buffer
): Promise<Buffer> {
  await verifyManifest(manifest, shardDir);

  const k = manifest.rs.data_shards;
  const shards = [...manifest.shards].sort((a, b) => a.index - b.index);
  const selected = shards.slice(0, k);

  const buffers: Buffer[] = [];
  for (const shard of selected) {
    if (!shard.path) throw new ManifestError("Shard missing path");
    buffers.push(await fs.readFile(join(shardDir, shard.path)));
  }

  // Demo reconstruction: concatenate first k shards
  let reconstructed = Buffer.concat(buffers).subarray(0, manifest.original_size_bytes);

  if (manifest.encryption) {
    throw new ManifestError("AES-GCM decryption not implemented in the TS stub yet");
  }

  return reconstructed;
}
