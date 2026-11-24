import test from 'node:test';
import assert from 'node:assert/strict';
import { RateLimiter } from '../../src/oba/limiter.js';

test('RateLimiter', async (t) => {
  await t.test('jobs run one at a time and resolve with their return values in order scheduled when same priority', async () => {
    let fakeTime = 0;
    const now = () => fakeTime;
    const sleep = (ms) => Promise.resolve((fakeTime += ms));

    const limiter = new RateLimiter({ minIntervalMs: 0, now, sleep });
    const results = [];

    // Schedule three jobs with same priority
    const p1 = limiter.schedule(() => {
      results.push('job1');
      return 'result1';
    });
    const p2 = limiter.schedule(() => {
      results.push('job2');
      return 'result2';
    });
    const p3 = limiter.schedule(() => {
      results.push('job3');
      return 'result3';
    });

    const [r1, r2, r3] = await Promise.all([p1, p2, p3]);

    assert.deepEqual(results, ['job1', 'job2', 'job3']);
    assert.equal(r1, 'result1');
    assert.equal(r2, 'result2');
    assert.equal(r3, 'result3');
  });

  await t.test('consecutive job starts are spaced >= minIntervalMs on fake clock', async () => {
    let fakeTime = 0;
    const now = () => fakeTime;
    const sleep = (ms) => Promise.resolve((fakeTime += ms));

    const limiter = new RateLimiter({ minIntervalMs: 100, now, sleep });
    const startTimes = [];

    limiter.schedule(() => {
      startTimes.push(fakeTime);
      return 'job1';
    });
    limiter.schedule(() => {
      startTimes.push(fakeTime);
      return 'job2';
    });
    limiter.schedule(() => {
      startTimes.push(fakeTime);
      return 'job3';
    });

    // Wait for all jobs to complete
    await new Promise((resolve) => {
      const check = () => {
        if (limiter.stats.executed === 3) resolve();
        else setTimeout(check, 1);
      };
      check();
    });

    assert.equal(startTimes.length, 3);
    // First job starts at time 0
    assert.equal(startTimes[0], 0);
    // Second job starts at time 100 (first + minIntervalMs)
    assert.equal(startTimes[1], 100);
    // Third job starts at time 200 (second + minIntervalMs)
    assert.equal(startTimes[2], 200);
  });

  await t.test('lower priority number runs first when several jobs queued before pump starts', async () => {
    let fakeTime = 0;
    const now = () => fakeTime;
    const sleep = (ms) => Promise.resolve((fakeTime += ms));

    const limiter = new RateLimiter({ minIntervalMs: 0, now, sleep });
    const runOrder = [];

    // Create a promise that we'll resolve to make the first job complete
    let releaseFirstJob;
    const firstJobPromise = new Promise((resolve) => {
      releaseFirstJob = resolve;
    });

    // Schedule a slow async job with priority 1 that blocks while queuing others
    const p1 = limiter.schedule(async () => {
      runOrder.push('priority1');
      await firstJobPromise;  // Wait for external signal to continue
      return 'slow';
    }, { priority: 1 });

    // While the first job is blocked, queue jobs with priority 2 and 0
    // The queue will sort these, putting 0 before 2
    const p2 = limiter.schedule(() => {
      runOrder.push('priority2');
      return 'p2';
    }, { priority: 2 });

    const p3 = limiter.schedule(() => {
      runOrder.push('priority0');
      return 'p0';
    }, { priority: 0 });

    // Release the first job so pump can continue processing remaining jobs
    releaseFirstJob();

    await Promise.all([p1, p2, p3]);

    // Priority 0 should run before priority 2 (after priority 1 completes)
    assert.equal(runOrder[0], 'priority1');
    assert.equal(runOrder[1], 'priority0');
    assert.equal(runOrder[2], 'priority2');
  });

  await t.test('a job that throws rejects its promise but subsequent jobs still run', async () => {
    let fakeTime = 0;
    const now = () => fakeTime;
    const sleep = (ms) => Promise.resolve((fakeTime += ms));

    const limiter = new RateLimiter({ minIntervalMs: 0, now, sleep });
    const results = [];

    const p1 = limiter.schedule(() => {
      results.push('job1');
      return 'result1';
    });

    const p2 = limiter.schedule(() => {
      results.push('job2-before-throw');
      throw new Error('intentional error');
    });

    const p3 = limiter.schedule(() => {
      results.push('job3');
      return 'result3';
    });

    const r1 = await p1;
    assert.equal(r1, 'result1');

    // Job 2 should reject
    let job2Error = null;
    try {
      await p2;
    } catch (e) {
      job2Error = e.message;
    }
    assert.equal(job2Error, 'intentional error');

    const r3 = await p3;
    assert.equal(r3, 'result3');

    // All jobs should have run despite the error
    assert.deepEqual(results, ['job1', 'job2-before-throw', 'job3']);
    // Stats should show executed and failed counts
    assert.equal(limiter.stats.executed, 2);
    assert.equal(limiter.stats.failed, 1);
  });

  await t.test('pause(ms) delays the next job start until now+ms', async () => {
    let fakeTime = 0;
    const now = () => fakeTime;
    const sleep = (ms) => Promise.resolve((fakeTime += ms));

    const limiter = new RateLimiter({ minIntervalMs: 0, now, sleep });
    const startTimes = [];

    limiter.schedule(() => {
      startTimes.push(fakeTime);
      return 'job1';
    });

    limiter.schedule(() => {
      startTimes.push(fakeTime);
      // Pause for 200ms - next job can't start before time 200
      limiter.pause(200);
      return 'job2';
    });

    limiter.schedule(() => {
      startTimes.push(fakeTime);
      return 'job3';
    });

    // Wait for all jobs
    await new Promise((resolve) => {
      const check = () => {
        if (limiter.stats.executed === 3) resolve();
        else setTimeout(check, 1);
      };
      check();
    });

    assert.equal(startTimes.length, 3);
    assert.equal(startTimes[0], 0); // First job starts at 0
    assert.equal(startTimes[1], 0); // Second job starts at 0 (no interval between 1 and 2)
    assert.equal(startTimes[2], 200); // Third job can't start before 200 due to pause
  });
});
