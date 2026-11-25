export interface DownloadOption {
  quality: string;
  url: string;
  sizeBytes?: number | null;
}

export interface VideoMetadata {
  id: string;
  title: string;
  thumbnailUrl?: string | null;
  durationSeconds?: number | null;
  options: DownloadOption[];
}
