import { VideoMetadata } from '../types';
import { fetchTweetMetadata as fetchMockMetadata } from './mockApi';

const API_BASE_URL = 'http://localhost:8000';

export const fetchTweetMetadata = async (url: string): Promise<VideoMetadata> => {
  // 1. Attempt to call the real Python backend
  try {
    // Create a timeout for the fetch request. 
    // Increased to 15000ms because yt-dlp extraction can take a few seconds.
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 15000);

    const response = await fetch(`${API_BASE_URL}/api/video`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ url, include_mp3: true }),
      signal: controller.signal,
    });

    clearTimeout(timeoutId);

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || 'Failed to fetch video from server');
    }

    const data = await response.json();
    return data;

  } catch (error) {
    // 2. If backend fails (offline/network error), fall back to Mock API for demo purposes
    console.warn('Backend unreachable (using mock data):', error);
    return fetchMockMetadata(url);
  }
};
