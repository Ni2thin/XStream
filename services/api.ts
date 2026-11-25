import type { VideoMetadata } from '../types';
import { API_BASE_URL } from '../config';

const BACKEND_STARTUP_TIMEOUT_MS = 90_000;
const HEALTH_REQUEST_TIMEOUT_MS = 8_000;
const HEALTH_RETRY_DELAY_MS = 3_000;

export const waitForBackend = async (): Promise<void> => {
  const deadline = performance.now() + BACKEND_STARTUP_TIMEOUT_MS;

  while (performance.now() < deadline) {
    const controller = new AbortController();
    const requestTimeout = Math.min(HEALTH_REQUEST_TIMEOUT_MS, deadline - performance.now());
    const timeoutId = setTimeout(() => controller.abort(), requestTimeout);

    try {
      const response = await fetch(`${API_BASE_URL}/health`, {
        cache: 'no-store',
        signal: controller.signal,
      });
      if (response.ok) {
        const health = await response.json();
        if (health?.status === 'ok' && health.service === 'xstream-backend') {
          return;
        }
      }
    } catch {
      // During startup Render can return a loading page or a connection error.
    } finally {
      clearTimeout(timeoutId);
    }

    const delay = Math.min(HEALTH_RETRY_DELAY_MS, deadline - performance.now());
    if (delay > 0) {
      await new Promise<void>(resolve => setTimeout(resolve, delay));
    }
  }

  throw new Error('The downloader is taking longer than expected to start. Try again in a moment.');
};

export const fetchTweetMetadata = async (url: string): Promise<VideoMetadata> => {
  const controller = new AbortController();
  // Give the backend time to finish its 30-second extraction attempt.
  const timeoutId = setTimeout(() => controller.abort(), 35_000);

  try {
    const response = await fetch(`${API_BASE_URL}/api/video`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ url: url.trim(), include_mp3: true }),
      signal: controller.signal,
    });

    if (response.status === 422) {
      throw new Error('Enter a valid X or Twitter post link.');
    }
    if (response.status === 400) {
      const { detail } = await response.json().catch(() => ({}));
      throw new Error(typeof detail === 'string' ? detail : 'Could not find a video on this post.');
    }
    if (response.status === 504) {
      throw new Error('X took too long to respond. Please try again.');
    }
    if (!response.ok) {
      throw new Error('The downloader is temporarily unavailable. Please try again.');
    }

    return await response.json();
  } catch (error) {
    if (controller.signal.aborted) {
      throw new Error('This request took too long. Please try again.');
    }
    if (error instanceof TypeError) {
      throw new Error('Could not reach the downloader. Check your connection and try again.');
    }
    throw error;
  } finally {
    clearTimeout(timeoutId);
  }
};
