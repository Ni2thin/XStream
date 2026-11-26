import { readFileSync } from 'node:fs';
import { expect, test } from '@playwright/test';
import type { VideoMetadata } from '../types';

const post = 'https://x.com/example/status/42';
const healthy = { status: 'ok', service: 'xstream-backend' };
const video = readFileSync(new URL('./fixtures/preview.mp4', import.meta.url));
const clips = [
  {
    id: 'first', title: 'First clip', playlistIndex: 1,
    options: [
      { quality: '720p', url: 'https://video.twimg.com/first.mp4' },
      { quality: '320kbps', url: 'mp3:' + post },
    ],
  },
  {
    id: 'second', title: 'Second clip', playlistIndex: 3,
    options: [
      { quality: '720p', url: 'https://video.twimg.com/second.mp4' },
      { quality: '360p', url: 'https://video.twimg.com/second-360.mp4' },
      { quality: '320kbps', url: 'mp3:' + post },
    ],
  },
];
const metadata: VideoMetadata = { ...clips[0], clips };

test.beforeEach(async ({ context, page }) => {
  // The fixture exercises the app without fetching CDN scripts or real posts.
  await context.route(/^https:\/\//, route => route.abort());
  await context.route('**/health', route => route.fulfill({ json: healthy }));
  await context.route('**/api/video', route => route.fulfill({ json: metadata }));
  await page.goto('/');
});

test('waits through a cold start before sending one extraction', async ({ page }) => {
  let checks = 0;
  let extractions = 0;
  await page.route('**/health', route => {
    checks += 1;
    if (checks === 1) return route.fulfill({ status: 503 });
    if (checks === 2) return route.fulfill({ contentType: 'text/html', body: '<p>Starting</p>' });
    return route.fulfill({ json: healthy });
  });
  await page.route('**/api/video', route => {
    expect(checks).toBe(3);
    extractions += 1;
    return route.fulfill({ json: metadata });
  });

  await page.getByRole('textbox', { name: 'X post link' }).fill(post);
  await page.getByRole('button', { name: 'Find video' }).click();
  await expect(page.getByRole('status')).toContainText('Starting the downloader');
  await expect(page.getByRole('heading', { name: 'Videos in this post' })).toBeVisible({ timeout: 13_000 });
  expect(extractions).toBe(1);
});

test('an invalid link stays available to edit or retry', async ({ page }) => {
  await page.route('**/api/video', route => route.fulfill({
    status: 422,
    json: { detail: 'Invalid X post' },
  }));
  const textbox = page.getByRole('textbox', { name: 'X post link' });
  const invalidLink = 'https://example.com/video';
  await textbox.fill(invalidLink);
  await page.getByRole('button', { name: 'Find video' }).click();

  await expect(page.getByRole('alert')).toContainText('Enter a valid X or Twitter post link');
  await expect(textbox).toHaveValue(invalidLink);
  await expect(page.getByRole('button', { name: 'Try again' })).toBeEnabled();
});

test('a selected clip previews on demand and can seek', async ({ context, page }) => {
  let previewRequests = 0;
  await context.route('**/api/preview?*', route => {
    previewRequests += 1;
    const url = new URL(route.request().url());
    expect(url.searchParams.get('url')).toBe('https://video.twimg.com/second.mp4');

    const range = route.request().headers().range?.match(/^bytes=(\d+)-(\d*)$/);
    const start = range ? Number(range[1]) : 0;
    const end = range?.[2] ? Math.min(Number(range[2]), video.length - 1) : video.length - 1;
    const body = video.subarray(start, end + 1);
    return route.fulfill({
      status: range ? 206 : 200,
      headers: {
        'Content-Type': 'video/mp4',
        'Accept-Ranges': 'bytes',
        'Content-Length': String(body.length),
        ...(range ? { 'Content-Range': 'bytes ' + start + '-' + end + '/' + video.length } : {}),
      },
      body,
    });
  });
  await page.getByRole('textbox', { name: 'X post link' }).fill(post);
  await page.getByRole('button', { name: 'Find video' }).click();
  const second = page.getByRole('region', { name: 'Second clip' });
  await expect(page.getByRole('region', { name: 'First clip' })).toBeVisible();
  await expect(second).toHaveCSS('border-radius', '24px');
  await expect(second.getByRole('link', { name: /Download MP4.*720p/ })).toBeVisible();
  expect(previewRequests).toBe(0);

  await second.getByRole('button', { name: 'Play preview' }).click();
  const player = second.locator('video');
  await expect.poll(() => player.evaluate(element => (element as HTMLVideoElement).readyState)).toBeGreaterThan(0);
  await player.evaluate(element => {
    const media = element as HTMLVideoElement;
    media.pause();
    media.currentTime = 2.5;
  });
  await expect.poll(() => player.evaluate(element => {
    const media = element as HTMLVideoElement;
    return !media.seeking && Math.abs(media.currentTime - 2.5) < 0.1;
  })).toBe(true);
  expect(previewRequests).toBeGreaterThan(0);
});

test('native MP4 saves with the chosen clip and quality', async ({ page }) => {
  await page.getByRole('textbox', { name: 'X post link' }).fill(post);
  await page.getByRole('button', { name: 'Find video' }).click();
  const second = page.getByRole('region', { name: 'Second clip' });
  await second.getByText('More formats', { exact: true }).click();
  const [download, request] = await Promise.all([
    page.waitForEvent('download'),
    page.waitForRequest('**/api/download?*'),
    second.getByRole('link', { name: /Download MP4 360p/ }).click(),
  ]);
  const params = new URL(request.url()).searchParams;
  expect(params.get('post_url')).toBe(post);
  expect(params.get('url')).toBe('https://video.twimg.com/second-360.mp4');
  expect(params.get('clip_id')).toBe('second');
  expect(params.get('quality')).toBe('360p');
  expect(download.suggestedFilename()).toBe('Second clip - Clip 2 - 360p.mp4');
  expect(await download.failure()).toBeNull();
  await expect(second).toBeVisible();
});

test('MP3 retry keeps the original selected clip', async ({ context, page }) => {
  let attempts = 0;
  await context.route('**/api/download?*', route => {
    const params = new URL(route.request().url()).searchParams;
    expect(params.get('url')).toBe('mp3:' + post);
    expect(params.get('clip_id')).toBe('second');
    expect(params.get('clip_index')).toBe('3');
    attempts += 1;
    if (attempts === 1) return route.fulfill({ status: 503 });
    return route.fulfill({ contentType: 'audio/mpeg', body: Buffer.from('ID3 test audio') });
  });

  await page.getByRole('textbox', { name: 'X post link' }).fill(post);
  await page.getByRole('button', { name: 'Find video' }).click();
  const second = page.getByRole('region', { name: 'Second clip' });
  await second.getByText('More formats', { exact: true }).click();
  await second.getByRole('button', { name: /Download MP3/ }).click();
  await expect(second.getByRole('alert')).toContainText('The downloader is busy');
  const [download] = await Promise.all([
    page.waitForEvent('download'),
    second.getByRole('button', { name: 'Retry MP3' }).click(),
  ]);
  expect(download.suggestedFilename()).toBe('Second clip - Clip 2 - 320kbps.mp3');
  expect(await download.failure()).toBeNull();
  expect(attempts).toBe(2);
});
