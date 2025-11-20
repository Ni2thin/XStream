export interface DownloadOption {
  id: string;
  label: string;
  extension: 'mp4' | 'mp3';
  quality: string; // e.g., '1080p', '720p', '320kbps'
  size: string;
  isBest?: boolean;
  url?: string; // Direct download link from backend
}

export interface VideoMetadata {
  id: string;
  originalUrl: string;
  title: string;
  thumbnailUrl: string;
  previewUrl: string;
  duration: string;
  author: string;
  avatarUrl: string;
  options: DownloadOption[];
  aspectRatio: '16:9' | '9:16' | '1:1';
  type: 'video' | 'audio';
}

export interface ApiError {
  message: string;
}