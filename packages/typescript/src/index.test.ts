/**
 * Tests for Nebula Reconstruction Kit - TypeScript SDK
 */

import { describe, it, expect, beforeAll } from "vitest";
import { join } from "path";
import { mkdirSync, writeFileSync, rmSync, existsSync } from "fs";
import { createHash } from "crypto";
import {
  loadManifest,
  verifyManifest,
  reconstructFile,
  computeMerkleRoot,
  analyzeReconstruction,
  analyzeRecoverability,
  loadAndVerifyShards,
  ManifestError,
  type ReconstructionManifest,
} from "./index";

const TEST_VECTORS_DIR = join(__dirname, "../../../test-vectors");
const TMP_DIR = join(__dirname, "../.test-tmp");

// Helper to create test shards
function createTestShards(
  tmpDir: string,
  data: Buffer,
  k: number = 3,
  n: number = 5
): ReconstructionManifest {
  const shardsDir = join(tmpDir, "shards");
  if (!existsSync(shardsDir)) {
    mkdirSync(shardsDir, { recursive: true });
  }

  // Simple split (demo, not real RS)
  const shardSize = Math.ceil(data.length / k);
  const paddedData = Buffer.concat([data, Buffer.alloc(shardSize * k - data.length)]);

  const shards: ReconstructionManifest["shards"] = [];
  const leafHashes: string[] = [];

  for (let i = 0; i < n; i++) {
    let shardData: Buffer;
    if (i < k) {
      shardData = paddedData.subarray(i * shardSize, (i + 1) * shardSize);
    } else {
      // Parity shard (demo: just zeros)
      shardData = Buffer.alloc(shardSize);
    }

    const shardPath = `shard-${i}.bin`;
    const shardHash = createHash("sha256").update(shardData).digest("hex");

    writeFileSync(join(shardsDir, shardPath), shardData);

    shards.push({
      index: i,
      hash: shardHash,
      size_bytes: shardData.length,
      path: `shards/${shardPath}`,
    });
    leafHashes.push(shardHash);
  }

  const merkleRoot = computeMerkleRoot(leafHashes);

  return {
    version: "nebula_reconstruct_v1",
    hash_algorithm: "sha256",
    original_size_bytes: data.length,
    original_hash: createHash("sha256").update(data).digest("hex"),
    rs: {
      data_shards: k,
      parity_shards: n - k,
      total_shards: n,
    },
    shards,
    merkle: {
      algorithm: "sha256",
      root: merkleRoot,
      leaf_hashes: leafHashes,
    },
  };
}

describe("loadManifest", () => {
  it("should load valid manifest from test-vectors", async () => {
    const manifest = await loadManifest(join(TEST_VECTORS_DIR, "manifest.json"));
    expect(manifest.version).toBe("nebula_reconstruct_v1");
    expect(manifest.rs.data_shards).toBe(3);
    expect(manifest.shards).toHaveLength(3);
  });
});

describe("verifyManifest", () => {
  it("should verify manifest with valid shards", async () => {
    const manifest = await loadManifest(join(TEST_VECTORS_DIR, "manifest.json"));
    await expect(verifyManifest(manifest, TEST_VECTORS_DIR)).resolves.not.toThrow();
  });
});

describe("computeMerkleRoot", () => {
  it("should compute correct merkle root from test vectors", async () => {
    const manifest = await loadManifest(join(TEST_VECTORS_DIR, "manifest.json"));
    const leaves = manifest.merkle?.leaf_hashes || [];
    const root = computeMerkleRoot(leaves);
    expect(root).toBe(manifest.merkle?.root);
  });

  it("should return empty string for no leaves", () => {
    expect(computeMerkleRoot([])).toBe("");
  });

  it("should return leaf for single element", () => {
    const leaf = createHash("sha256").update("test").digest("hex");
    expect(computeMerkleRoot([leaf])).toBe(leaf);
  });

  it("should compute root for two leaves", () => {
    const leaf1 = createHash("sha256").update("leaf1").digest("hex");
    const leaf2 = createHash("sha256").update("leaf2").digest("hex");

    const combined = Buffer.concat([Buffer.from(leaf1, "hex"), Buffer.from(leaf2, "hex")]);
    const expected = createHash("sha256").update(combined).digest("hex");

    expect(computeMerkleRoot([leaf1, leaf2])).toBe(expected);
  });
});

describe("analyzeReconstruction", () => {
  it("should report feasible when enough shards", () => {
    const result = analyzeReconstruction([0, 2, 4], 3, 5);
    expect(result.feasible).toBe(true);
    expect(result.availableShards).toBe(3);
    expect(result.requiredShards).toBe(3);
  });

  it("should report not feasible when too few shards", () => {
    const result = analyzeReconstruction([0, 1], 3, 5);
    expect(result.feasible).toBe(false);
    expect(result.message).toContain("more shard");
  });

  it("should detect fast path when all data shards present", () => {
    const result = analyzeReconstruction([0, 1, 2], 3, 5);
    expect(result.fastPath).toBe(true);
  });

  it("should not detect fast path when data shard missing", () => {
    const result = analyzeReconstruction([0, 2, 3], 3, 5);
    expect(result.fastPath).toBe(false);
    expect(result.feasible).toBe(true);
  });

  it("should calculate redundancy margin", () => {
    const result = analyzeReconstruction([0, 1, 2, 3, 4], 3, 5);
    expect(result.redundancyMargin).toBe(2);
  });
});

describe("reconstructFile (from test-vectors)", () => {
  it("should reconstruct file from demo shards", async () => {
    const manifest = await loadManifest(join(TEST_VECTORS_DIR, "manifest.json"));
    const { data, report } = await reconstructFile(manifest, TEST_VECTORS_DIR, undefined, false);

    expect(data.length).toBe(39);
    expect(data.toString()).toBe("hello shard0\nhello shard1\nhello shard2\n");
    expect(report.success).toBe(true);
    expect(report.shardsValid).toBe(3);
  });
});

describe("reconstructFile (with temp shards)", () => {
  beforeAll(() => {
    if (existsSync(TMP_DIR)) {
      rmSync(TMP_DIR, { recursive: true });
    }
    mkdirSync(TMP_DIR, { recursive: true });
  });

  it("should reconstruct simple data", async () => {
    const original = Buffer.from("Hello, World! Test data for reconstruction.");
    const manifest = createTestShards(TMP_DIR, original, 3, 5);

    const { data, report } = await reconstructFile(manifest, TMP_DIR);

    expect(data).toEqual(original);
    expect(report.success).toBe(true);
    expect(report.hashVerified).toBe(true);
  });

  it("should verify hash of reconstructed data", async () => {
    const original = Buffer.from("Data with hash verification");
    const manifest = createTestShards(TMP_DIR, original, 3, 5);

    const { report } = await reconstructFile(manifest, TMP_DIR, undefined, true);

    expect(report.hashVerified).toBe(true);
    expect(report.reconstructedHash).toBe(manifest.original_hash);
  });
});

describe("loadAndVerifyShards", () => {
  it("should load and verify all shards", async () => {
    const manifest = await loadManifest(join(TEST_VECTORS_DIR, "manifest.json"));
    const shards = await loadAndVerifyShards(manifest, TEST_VECTORS_DIR);

    expect(shards).toHaveLength(3);
    expect(shards.every((s) => s.valid)).toBe(true);
    expect(shards.every((s) => s.data !== undefined)).toBe(true);
  });
});

describe("analyzeRecoverability", () => {
  it("should analyze with shard directory", async () => {
    const manifest = await loadManifest(join(TEST_VECTORS_DIR, "manifest.json"));
    const analysis = await analyzeRecoverability(manifest, TEST_VECTORS_DIR);

    expect(analysis.feasible).toBe(true);
    expect(analysis.shardsValid).toBe(3);
    expect(analysis.k).toBe(3);
    expect(analysis.n).toBe(3);
  });

  it("should analyze without shard directory", async () => {
    const manifest = await loadManifest(join(TEST_VECTORS_DIR, "manifest.json"));
    const analysis = await analyzeRecoverability(manifest);

    expect(analysis.feasible).toBe(true);
    expect(analysis.note).toContain("not verified");
  });
});
