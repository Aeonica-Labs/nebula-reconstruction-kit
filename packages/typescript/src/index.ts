/**
 * Nebula Reconstruction Kit - TypeScript SDK
 *
 * Zero-lock-in toolkit for verifying and reconstructing data from Nebula shards.
 *
 * Where `nebula-proof-kit` answers "Is this proof cryptographically valid?",
 * this kit answers "Can we actually recover the data?"
 */

import { createHash, createDecipheriv } from "crypto";
import { promises as fs } from "fs";
import { join } from "path";

// ============================================================================
// Types
// ============================================================================

export interface ReconstructionManifest {
  version: string;
  hash_algorithm: "sha256";
  original_size_bytes: number;
  original_hash?: string;
  rs: {
    data_shards: number;
    parity_shards: number;
    total_shards: number;
  };
  shards: Array<{
    index: number;
    hash: string;
    size_bytes?: number;
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

export interface ShardInfo {
  index: number;
  path: string;
  expectedHash: string;
  actualHash?: string;
  data?: Buffer;
  valid: boolean;
  error?: string;
}

export interface ReconstructionReport {
  success: boolean;
  feasible: boolean;
  originalSize: number;
  reconstructedSize: number;
  originalHash?: string;
  reconstructedHash?: string;
  hashVerified: boolean;
  decrypted: boolean;
  shardsRequired: number;
  shardsAvailable: number;
  shardsValid: number;
  shardDetails: ShardInfo[];
  error?: string;
}

export interface RecoverabilityAnalysis {
  k: number;
  n: number;
  originalSize: number;
  originalHash?: string;
  shardsDeclared: number;
  shardsFound?: number;
  shardsValid?: number;
  validIndices?: number[];
  feasible: boolean;
  fastPath?: boolean;
  missingCount?: number;
  redundancyMargin?: number;
  message: string;
  shardStatus?: Array<{ index: number; valid: boolean; error?: string }>;
  note?: string;
}

export class ManifestError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ManifestError";
  }
}

// ============================================================================
// Manifest Operations
// ============================================================================

export async function loadManifest(path: string): Promise<ReconstructionManifest> {
  const raw = await fs.readFile(path, "utf-8");
  return JSON.parse(raw) as ReconstructionManifest;
}

export async function verifyManifest(
  manifest: ReconstructionManifest,
  shardDir?: string
): Promise<void> {
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
      if (digest !== shard.hash) {
        throw new ManifestError(`Shard hash mismatch: ${shard.path}`);
      }
    }
  }

  if (manifest.merkle?.root) {
    const root = computeMerkleRoot(manifest.merkle.leaf_hashes || []);
    if (root !== manifest.merkle.root) {
      throw new ManifestError("Merkle root mismatch");
    }
  }
}

// ============================================================================
// Merkle Tree
// ============================================================================

export function computeMerkleRoot(leaves: string[]): string {
  if (!leaves.length) return "";
  let layer: Buffer[] = leaves.map((h) => Buffer.from(h, "hex"));

  while (layer.length > 1) {
    if (layer.length % 2 === 1) {
      layer.push(layer[layer.length - 1]);
    }
    const next: Buffer[] = [];
    for (let i = 0; i < layer.length; i += 2) {
      const combined = Buffer.concat([layer[i], layer[i + 1]]);
      next.push(createHash("sha256").update(combined).digest() as Buffer);
    }
    layer = next;
  }

  return layer[0].toString("hex");
}

// ============================================================================
// Shard Operations
// ============================================================================

export async function loadAndVerifyShards(
  manifest: ReconstructionManifest,
  shardDir: string
): Promise<ShardInfo[]> {
  const shardInfos: ShardInfo[] = [];

  for (const shard of manifest.shards) {
    const info: ShardInfo = {
      index: shard.index,
      path: shard.path || "",
      expectedHash: shard.hash,
      valid: false,
    };

    if (!shard.path) {
      info.error = "Shard missing path";
      shardInfos.push(info);
      continue;
    }

    try {
      const shardPath = join(shardDir, shard.path);
      const data = await fs.readFile(shardPath);
      info.data = data;
      info.actualHash = createHash("sha256").update(data).digest("hex");

      if (info.actualHash === info.expectedHash) {
        info.valid = true;
      } else {
        info.error = `Hash mismatch: expected ${info.expectedHash.slice(0, 16)}..., got ${info.actualHash.slice(0, 16)}...`;
      }
    } catch (e) {
      info.error = e instanceof Error ? e.message : String(e);
    }

    shardInfos.push(info);
  }

  return shardInfos;
}

// ============================================================================
// Analysis
// ============================================================================

export function analyzeReconstruction(
  availableIndices: number[],
  k: number,
  n: number
): {
  feasible: boolean;
  availableShards: number;
  requiredShards: number;
  totalShards: number;
  missingShards: number[];
  missingCount: number;
  redundancyMargin: number;
  fastPath: boolean;
  message: string;
} {
  const availableSet = new Set(availableIndices);
  const missingShards = [];
  for (let i = 0; i < n; i++) {
    if (!availableSet.has(i)) missingShards.push(i);
  }

  const dataShardIndices = new Set(Array.from({ length: k }, (_, i) => i));
  const haveAllData = Array.from(dataShardIndices).every((i) => availableSet.has(i));

  const feasible = availableIndices.length >= k;

  return {
    feasible,
    availableShards: availableIndices.length,
    requiredShards: k,
    totalShards: n,
    missingShards,
    missingCount: missingShards.length,
    redundancyMargin: availableIndices.length - k,
    fastPath: haveAllData,
    message: feasible
      ? "Reconstruction possible"
      : `Need ${k - availableIndices.length} more shard(s)`,
  };
}

export async function analyzeRecoverability(
  manifest: ReconstructionManifest,
  shardDir?: string
): Promise<RecoverabilityAnalysis> {
  const { data_shards: k, total_shards: n } = manifest.rs;

  const result: RecoverabilityAnalysis = {
    k,
    n,
    originalSize: manifest.original_size_bytes,
    originalHash: manifest.original_hash,
    shardsDeclared: manifest.shards.length,
    feasible: false,
    message: "",
  };

  if (shardDir) {
    const shardInfos = await loadAndVerifyShards(manifest, shardDir);
    const validIndices = shardInfos.filter((s) => s.valid).map((s) => s.index);
    const analysis = analyzeReconstruction(validIndices, k, n);

    result.shardsFound = shardInfos.filter((s) => s.data !== undefined).length;
    result.shardsValid = validIndices.length;
    result.validIndices = validIndices;
    result.feasible = analysis.feasible;
    result.fastPath = analysis.fastPath;
    result.missingCount = analysis.missingCount;
    result.redundancyMargin = analysis.redundancyMargin;
    result.message = analysis.message;
    result.shardStatus = shardInfos.map((s) => ({
      index: s.index,
      valid: s.valid,
      error: s.error,
    }));
  } else {
    const declaredIndices = manifest.shards.map((s) => s.index);
    const analysis = analyzeReconstruction(declaredIndices, k, n);
    result.feasible = analysis.feasible;
    result.message = analysis.message;
    result.note = "Actual shard availability not verified (no shardDir provided)";
  }

  return result;
}

// ============================================================================
// Decryption
// ============================================================================

function decryptAES256GCM(
  ciphertext: Buffer<ArrayBuffer>,
  key: Buffer<ArrayBuffer>,
  iv: Buffer<ArrayBuffer>,
  tag: Buffer<ArrayBuffer>
): Buffer<ArrayBuffer> {
  const decipher = createDecipheriv("aes-256-gcm", key, iv);
  decipher.setAuthTag(tag);
  const decrypted = Buffer.concat([decipher.update(ciphertext), decipher.final()]) as Buffer<ArrayBuffer>;
  return decrypted;
}

// ============================================================================
// Reconstruction
// ============================================================================

export async function reconstructFile(
  manifest: ReconstructionManifest,
  shardDir: string,
  key?: Buffer,
  verifyHash: boolean = true
): Promise<{ data: Buffer; report: ReconstructionReport }> {
  const { data_shards: k, total_shards: n } = manifest.rs;
  const originalSize = manifest.original_size_bytes;
  const originalHash = manifest.original_hash;

  // Load and verify shards
  const shardInfos = await loadAndVerifyShards(manifest, shardDir);
  const validShards = shardInfos.filter((s) => s.valid);

  const report: ReconstructionReport = {
    success: false,
    feasible: validShards.length >= k,
    originalSize,
    reconstructedSize: 0,
    originalHash,
    reconstructedHash: undefined,
    hashVerified: false,
    decrypted: false,
    shardsRequired: k,
    shardsAvailable: shardInfos.filter((s) => s.data !== undefined).length,
    shardsValid: validShards.length,
    shardDetails: shardInfos,
  };

  if (!report.feasible) {
    report.error = `Need ${k} valid shards, only ${validShards.length} available`;
    throw new ManifestError(report.error);
  }

  // Sort by index and take first k
  validShards.sort((a, b) => a.index - b.index);
  const selectedShards = validShards.slice(0, k);

  // Demo reconstruction: concatenate first k data shards
  // Note: For full RS decoding with parity, would need RS library
  const buffers = selectedShards.map((s) => s.data!);
  let reconstructed = Buffer.concat(buffers).subarray(0, originalSize);

  // Handle encryption
  if (manifest.encryption) {
    if (manifest.encryption.algorithm !== "aes-256-gcm") {
      report.error = `Unsupported encryption: ${manifest.encryption.algorithm}`;
      throw new ManifestError(report.error);
    }

    if (!key) {
      report.error = "Decryption key required but not provided";
      throw new ManifestError(report.error);
    }

    if (!manifest.encryption.iv) {
      report.error = "Missing IV for AES-GCM";
      throw new ManifestError(report.error);
    }

    try {
      const iv = Buffer.from(manifest.encryption.iv, "hex") as Buffer<ArrayBuffer>;

      // Tag can be appended to ciphertext or separate
      let ciphertext: Buffer<ArrayBuffer>;
      let tag: Buffer<ArrayBuffer>;

      if (manifest.encryption.tag) {
        ciphertext = reconstructed as Buffer<ArrayBuffer>;
        tag = Buffer.from(manifest.encryption.tag, "hex") as Buffer<ArrayBuffer>;
      } else {
        // Tag is last 16 bytes of ciphertext
        ciphertext = reconstructed.subarray(0, -16) as Buffer<ArrayBuffer>;
        tag = reconstructed.subarray(-16) as Buffer<ArrayBuffer>;
      }

      reconstructed = decryptAES256GCM(ciphertext, key as Buffer<ArrayBuffer>, iv, tag);
      report.decrypted = true;
    } catch (e) {
      report.error = `Decryption failed: ${e instanceof Error ? e.message : String(e)}`;
      throw new ManifestError(report.error);
    }
  }

  report.reconstructedSize = reconstructed.length;
  report.reconstructedHash = createHash("sha256").update(reconstructed).digest("hex");

  // Verify hash
  if (verifyHash && originalHash) {
    report.hashVerified = report.reconstructedHash === originalHash;
    if (!report.hashVerified) {
      report.error = `Hash mismatch: expected ${originalHash.slice(0, 16)}..., got ${report.reconstructedHash.slice(0, 16)}...`;
      throw new ManifestError(report.error);
    }
  }

  report.success = true;
  return { data: reconstructed, report };
}
