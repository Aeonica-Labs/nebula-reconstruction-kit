/**
 * Tests for Nebula Reconstruction Kit
 */

import { describe, it, expect } from 'vitest';
import { join } from 'path';
import { loadManifest, verifyManifest, reconstructFile, computeMerkleRoot } from './index';

const TEST_VECTORS_DIR = join(__dirname, '../../../test-vectors');

describe('loadManifest', () => {
  it('should load valid manifest', async () => {
    const manifest = await loadManifest(join(TEST_VECTORS_DIR, 'manifest.json'));
    expect(manifest.version).toBe('nebula_reconstruct_v1');
    expect(manifest.rs.data_shards).toBe(3);
    expect(manifest.shards).toHaveLength(3);
  });
});

describe('verifyManifest', () => {
  it('should verify manifest with valid shards', async () => {
    const manifest = await loadManifest(join(TEST_VECTORS_DIR, 'manifest.json'));
    await expect(verifyManifest(manifest, TEST_VECTORS_DIR)).resolves.not.toThrow();
  });
});

describe('computeMerkleRoot', () => {
  it('should compute correct merkle root', async () => {
    const manifest = await loadManifest(join(TEST_VECTORS_DIR, 'manifest.json'));
    const leaves = manifest.merkle?.leaf_hashes || [];
    const root = computeMerkleRoot(leaves);
    expect(root).toBe(manifest.merkle?.root);
  });
});

describe('reconstructFile', () => {
  it('should reconstruct file from shards', async () => {
    const manifest = await loadManifest(join(TEST_VECTORS_DIR, 'manifest.json'));
    const data = await reconstructFile(manifest, TEST_VECTORS_DIR);
    expect(data.length).toBe(39);
    expect(data.toString()).toBe('hello shard0\nhello shard1\nhello shard2\n');
  });
});
