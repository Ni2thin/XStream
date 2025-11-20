import { VideoMetadata } from '../types';

// In a real production app, this would call your backend endpoint which handles the actual scraping/API interaction with X.
// Since we are client-side only for this demo, we mock the response.

const MOCK_THUMBNAILS = [
  "https://picsum.photos/seed/tweet1/1280/720", // 16:9
  "https://picsum.photos/seed/tweet2/720/1280", // 9:16
  "https://picsum.photos/seed/tweet3/800/800"   // 1:1
];

// Sample public domain video for preview functionality
const SAMPLE_VIDEO = "https://storage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4";

export const fetchTweetMetadata = async (url: string): Promise<VideoMetadata> => {
  return new Promise((resolve, reject) => {
    // Simulate network delay
    setTimeout(() => {
      // Basic validation
      if (!url.includes('twitter.com') && !url.includes('x.com')) {
        reject({ message: 'Invalid URL. Please paste a valid X (Twitter) link.' });
        return;
      }

      // Simulate extraction success
      const isShort = Math.random() > 0.5;
      const aspectRatio = isShort ? '9:16' : '16:9';
      
      const mockData: VideoMetadata = {
        id: Math.random().toString(36).substring(7),
        originalUrl: url,
        title: "Amazing footage from the event! You won't believe what happened next. #viral #video",
        thumbnailUrl: isShort ? MOCK_THUMBNAILS[1] : MOCK_THUMBNAILS[0],
        previewUrl: SAMPLE_VIDEO,
        duration: "0:45",
        author: "@CreativeUser",
        avatarUrl: `https://api.dicebear.com/7.x/avataaars/svg?seed=${Math.random()}`,
        aspectRatio: aspectRatio,
        type: 'video',
        options: [
          {
            id: '1',
            label: 'High Definition',
            extension: 'mp4',
            quality: '1080p',
            size: '24.5 MB',
            isBest: true
          },
          {
            id: '2',
            label: 'Standard Definition',
            extension: 'mp4',
            quality: '720p',
            size: '12.1 MB'
          },
          {
            id: '3',
            label: 'Mobile Optimized',
            extension: 'mp4',
            quality: '480p',
            size: '5.4 MB'
          },
          {
            id: '4',
            label: 'Audio Only',
            extension: 'mp3',
            quality: '320kbps',
            size: '3.2 MB'
          }
        ]
      };

      resolve(mockData);
    }, 1500);
  });
};