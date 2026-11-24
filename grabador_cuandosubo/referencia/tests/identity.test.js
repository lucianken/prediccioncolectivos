import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { Identity, baDate } from '../../src/identity.js';

test('Identity', async (t) => {
  const labelLineMap = {
    lines: {
      '151': {
        agencies: [
          { agencyId: '9', agencyName: 'Línea 9', from: '2026-03-28', to: '2026-06-10' },
          { agencyId: '708', agencyName: 'Línea 708', from: '2026-06-11', to: null },
        ],
        suffixes: [
          { suffix: '4045', agencyId: '9', from: '2026-03-28', to: '2026-05-29' },
          { suffix: '4852', agencyId: '708', from: '2026-06-11', to: null },
        ],
      },
      '65': {
        agencies: [
          { agencyId: '708', agencyName: 'Línea 708', from: '2026-03-28', to: null },
        ],
        suffixes: [
          { suffix: '4851', agencyId: '708', from: '2026-06-11', to: null },
        ],
      },
    },
  };

  await t.test('lineForLabel resolves label suffix to line', async () => {
    const identity = new Identity({ labelLineMap, registry: {} });

    // Label with suffix 4852 on 2026-10-19 should resolve to line 151
    assert.equal(identity.lineForLabel('433-4852', '2026-10-19'), '151');

    // Old suffix 4045 resolves on 2026-05-01 (within its date range)
    assert.equal(identity.lineForLabel('433-4045', '2026-05-01'), '151');

    // Old suffix 4045 does NOT resolve on 2026-10-19 (outside its date range)
    assert.equal(identity.lineForLabel('433-4045', '2026-10-19'), null);

    // Label without '-' returns null
    assert.equal(identity.lineForLabel('no-dash-label', '2026-10-19'), null);

    // null label returns null
    assert.equal(identity.lineForLabel(null, '2026-10-19'), null);
  });

  await t.test('agenciesFor returns only active agencies for a line on a date', async () => {
    const identity = new Identity({ labelLineMap, registry: {} });

    // On 2026-10-19, only agency 708 operates line 151
    const agencies1 = identity.agenciesFor('151', '2026-10-19');
    assert.deepEqual(agencies1, [
      { id: '708', name: 'Línea 708' },
    ]);

    // On 2026-05-01, only agency 9 operates line 151
    const agencies2 = identity.agenciesFor('151', '2026-05-01');
    assert.deepEqual(agencies2, [
      { id: '9', name: 'Línea 9' },
    ]);

    // On 2026-10-19, agency 708 operates line 65
    const agencies3 = identity.agenciesFor('65', '2026-10-19');
    assert.deepEqual(agencies3, [
      { id: '708', name: 'Línea 708' },
    ]);
  });

  await t.test('resolve with live label returns source oba', async () => {
    const identity = new Identity({ labelLineMap, registry: {} });

    const result = identity.resolve('vid123', '433-4852');
    assert.deepEqual(result, { label: '433-4852', source: 'oba' });
  });

  await t.test('resolve uses registry when no live label', async () => {
    const registry = { vid456: '433-4852' };
    const identity = new Identity({ labelLineMap, registry });

    const result = identity.resolve('vid456', null);
    assert.deepEqual(result, { label: '433-4852', source: 'registry' });
  });

  await t.test('resolve returns learned label when not in live or registry', async () => {
    const identity = new Identity({ labelLineMap, registry: {} });

    // Learn a label by resolving with live label
    identity.resolve('vid789', '433-4852');

    // Now resolve without live label should return learned label
    const result = identity.resolve('vid789', null);
    assert.deepEqual(result, { label: '433-4852', source: 'learned' });
  });

  await t.test('resolve returns null when label unknown', async () => {
    const identity = new Identity({ labelLineMap, registry: {} });

    const result = identity.resolve('unknown-vid', null);
    assert.deepEqual(result, { label: null, source: null });
  });

  await t.test('resolve learns live labels and records conflicts', async () => {
    const registry = { vid: 'old-label' };
    const identity = new Identity({ labelLineMap, registry });

    // First resolution with different label should record conflict
    identity.resolve('vid', 'new-label');

    assert.equal(identity.conflicts.length, 1);
    assert.equal(identity.conflicts[0].id, 'vid');
    assert.equal(identity.conflicts[0].known, 'old-label');
    assert.equal(identity.conflicts[0].seen, 'new-label');
  });

  await t.test('flush persists learned labels to file', async () => {
    const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'bondiradar-test-'));
    const learnedPath = path.join(tempDir, 'learned.json');

    const identity = new Identity({ labelLineMap, registry: {}, learnedPath });
    identity.resolve('vid1', '433-4852');
    identity.resolve('vid2', '100-4851');

    // Initially dirty, flush should return true
    const flushed = identity.flush();
    assert.equal(flushed, true);

    // File should exist and contain the learned labels
    assert.ok(fs.existsSync(learnedPath));
    const content = JSON.parse(fs.readFileSync(learnedPath, 'utf8'));
    assert.ok(content.learned.vid1);
    assert.equal(content.learned.vid1.label, '433-4852');
    assert.ok(content.learned.vid2);

    // Load in a new Identity with the same path
    const identity2 = new Identity({ labelLineMap, registry: {}, learnedPath });
    const result1 = identity2.resolve('vid1', null);
    assert.deepEqual(result1, { label: '433-4852', source: 'learned' });

    const result2 = identity2.resolve('vid2', null);
    assert.deepEqual(result2, { label: '100-4851', source: 'learned' });

    // Clean up
    fs.rmSync(tempDir, { recursive: true });
  });

  await t.test('flush returns false when nothing changed', async () => {
    const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'bondiradar-test-'));
    const learnedPath = path.join(tempDir, 'learned.json');

    const identity = new Identity({ labelLineMap, registry: {}, learnedPath });
    identity.resolve('vid1', '433-4852');
    identity.flush(); // First flush

    // Second flush with no changes should return false
    const flushed = identity.flush();
    assert.equal(flushed, false);

    // Clean up
    fs.rmSync(tempDir, { recursive: true });
  });
});

test('baDate', async (t) => {
  await t.test('converts UTC timestamp to Buenos Aires date', async () => {
    // Date.UTC(2026, 9, 20, 2, 0) = 2026-10-20T02:00:00Z
    // Buenos Aires is UTC-3, so this is 2026-10-19 23:00:00 in BA local time
    // Wait, let me recalculate: UTC-3 means 3 hours behind UTC
    // So 2026-10-20 02:00:00 UTC = 2026-10-19 23:00:00 BA time (one day earlier)
    // But we need to verify the exact conversion
    // The function: baDate(ms) = new Date(ms - 3 * 3600 * 1000).toISOString().slice(0, 10)
    // Date.UTC(2026, 9, 20, 2, 0) creates October 20, 2026 at 02:00:00 UTC
    // Subtracting 3 hours (3 * 3600 * 1000 ms) gives October 19, 2026 at 23:00:00 UTC
    // When converted to ISO string, this is 2026-10-19 (at 23:00 UTC, same day in UTC string)
    // Hmm, actually let me test it more carefully.

    // The function takes milliseconds and converts to BA date
    // BA is UTC-3, meaning BA time = UTC - 3 hours
    // So if we have a UTC timestamp, we subtract 3 hours to get BA local time equivalent
    // Then get the date part

    // Date.UTC(2026, 9, 20, 2, 0) ms is 2026-10-20T02:00:00Z
    // subtracting 3 hours: 2026-10-20T02:00:00Z - 3h = 2026-10-19T23:00:00Z
    // ISO string slice(0, 10) = "2026-10-19"
    const result = baDate(Date.UTC(2026, 9, 20, 2, 0));
    assert.equal(result, '2026-10-19');
  });

  await t.test('handles boundary cases around midnight', async () => {
    // 2026-10-20 00:00:00 UTC - 3h = 2026-10-19 21:00:00 UTC → "2026-10-19"
    assert.equal(baDate(Date.UTC(2026, 9, 20, 0, 0)), '2026-10-19');

    // 2026-10-20 03:00:00 UTC - 3h = 2026-10-20 00:00:00 UTC → "2026-10-20"
    assert.equal(baDate(Date.UTC(2026, 9, 20, 3, 0)), '2026-10-20');

    // 2026-10-20 02:59:59 UTC - 3h = 2026-10-19 23:59:59 UTC → "2026-10-19"
    assert.equal(baDate(Date.UTC(2026, 9, 20, 2, 59, 59, 999)), '2026-10-19');
  });
});
