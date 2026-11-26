export interface DownloadOption {
  quality: string;
  url: string;
  sizeBytes?: number | null;
}

export interface VideoClip {
  id: string;
  title: string;
  thumbnailUrl?: string | null;
  durationSeconds?: number | null;
  playlistIndex?: number | null;
  options: DownloadOption[];
}

export interface VideoMetadata extends VideoClip {
  clips?: VideoClip[];
}
