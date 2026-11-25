import { useEffect, useRef, useState } from 'react';
import type { MouseEvent } from 'react';
import { ArrowLeft, ChevronDown, Download, Music, Play, Video, X } from 'lucide-react';
import { API_BASE_URL } from '../config';
import type { DownloadOption, VideoMetadata } from '../types';
import { Button } from './Button';

interface DownloadCardProps {
  data: VideoMetadata;
  onReset: () => void;
}

type DownloadStatus = 'idle' | 'video-started' | 'converting' | 'saving' | 'audio-started' | 'audio-error';

const downloadMessages: Record<DownloadStatus, string> = {
  idle: '',
  'video-started': 'Check your browser’s downloads. If the MP4 doesn’t start, try the download again.',
  converting: 'Converting to MP3…',
  saving: 'Downloading MP3…',
  'audio-started': 'The MP3 is ready. Check your browser’s downloads.',
  'audio-error': 'Couldn’t finish the MP3 download.',
};

const optionDetails = ({ quality, sizeBytes }: DownloadOption) => {
  if (!sizeBytes || sizeBytes < 0) return quality;
  const size = sizeBytes < 1_000_000
    ? Math.round(sizeBytes / 1_000) + ' KB'
    : (sizeBytes / 1_000_000).toFixed(1) + ' MB';
  return quality + ' · ' + size;
};

const formatDuration = (seconds?: number | null) => {
  if (seconds == null || !Number.isFinite(seconds) || seconds < 0) return null;
  const totalSeconds = Math.round(seconds);
  return Math.floor(totalSeconds / 60) + ':' + String(totalSeconds % 60).padStart(2, '0');
};

export function DownloadCard({ data, onReset }: DownloadCardProps) {
  const [downloadStatus, setDownloadStatus] = useState<DownloadStatus>('idle');
  const [preview, setPreview] = useState<'closed' | 'playing' | 'error'>('closed');
  const [thumbnailFailed, setThumbnailFailed] = useState(false);
  const heading = useRef<HTMLHeadingElement>(null);
  const audioRequest = useRef<AbortController | null>(null);

  const [bestVideo, ...otherVideos] = data.options.filter(option => !option.url.startsWith('mp3:'));
  const audio = data.options.find(option => option.url.startsWith('mp3:'));
  const title = data.title.trim() || 'X video';
  const filename = title.slice(0, 100);
  const duration = formatDuration(data.durationSeconds);
  const isAudioBusy = downloadStatus === 'converting' || downloadStatus === 'saving';

  useEffect(() => {
    heading.current?.focus();
    return () => {
      const activeRequest = audioRequest.current;
      audioRequest.current = null;
      activeRequest?.abort();
    };
  }, []);

  const startAudioDownload = async () => {
    if (!audio || audioRequest.current) return;

    const controller = new AbortController();
    audioRequest.current = controller;
    // Leave time to deliver the file after the backend's 180-second conversion budget.
    const timeout = window.setTimeout(() => controller.abort(), 195_000);
    setDownloadStatus('converting');

    try {
      const params = new URLSearchParams({ url: audio.url });
      const response = await fetch(API_BASE_URL + '/api/download?' + params, { signal: controller.signal });
      if (!response.ok || !response.headers.get('Content-Type')?.startsWith('audio/')) {
        throw new Error('MP3 conversion failed');
      }

      setDownloadStatus('saving');
      const blob = await response.blob();
      if (audioRequest.current !== controller) return;

      const objectUrl = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = objectUrl;
      link.download = filename.replace(/[<>:"/\\|?*\u0000-\u001f\u007f]/g, '_') + ' - ' + audio.quality + '.mp3';
      document.body.append(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(objectUrl), 30_000);
      setDownloadStatus('audio-started');
    } catch {
      if (audioRequest.current === controller) {
        setDownloadStatus('audio-error');
      }
    } finally {
      window.clearTimeout(timeout);
      if (audioRequest.current === controller) {
        audioRequest.current = null;
      }
    }
  };

  const videoDownloadHref = (option: DownloadOption) => {
    const params = new URLSearchParams({
      url: option.url,
      filename: filename + ' - ' + option.quality,
    });
    return API_BASE_URL + '/api/download?' + params;
  };

  const startVideoDownload = (event: MouseEvent<HTMLAnchorElement>) => {
    if (audioRequest.current) {
      event.preventDefault();
      return;
    }
    setDownloadStatus('video-started');
  };

  return (
    <section aria-labelledby="result-title" className="w-full max-w-4xl overflow-hidden rounded-3xl border border-slate-200 bg-white text-left shadow-xl">
      <div className={bestVideo ? 'grid md:grid-cols-2' : ''}>
        {bestVideo && (
          <div className="bg-slate-100 md:flex md:items-center">
            <div className="relative aspect-video w-full overflow-hidden bg-slate-900">
              {preview === 'playing' ? (
                <video
                  src={API_BASE_URL + '/api/preview?' + new URLSearchParams({ url: bestVideo.url })}
                  aria-label="Video preview"
                  className="h-full w-full object-contain"
                  controls
                  autoPlay
                  playsInline
                  crossOrigin="anonymous"
                  onError={() => setPreview('error')}
                />
              ) : (
                <>
                  {data.thumbnailUrl && !thumbnailFailed ? (
                    <img
                      src={data.thumbnailUrl}
                      alt=""
                      referrerPolicy="no-referrer"
                      onError={() => setThumbnailFailed(true)}
                      className="absolute inset-0 h-full w-full object-contain"
                    />
                  ) : (
                    <Video aria-hidden="true" className="absolute left-4 top-4 h-5 w-5 text-slate-500" />
                  )}
                  {duration && (
                    <span className="absolute bottom-3 right-3 rounded-md bg-black/70 px-2 py-1 text-xs font-medium text-white">
                      {duration}
                    </span>
                  )}
                </>
              )}
              <button
                type="button"
                aria-label={preview === 'playing' ? 'Close preview' : 'Play preview'}
                aria-expanded={preview === 'playing'}
                onClick={() => setPreview(preview === 'playing' ? 'closed' : 'playing')}
                className={preview === 'playing'
                  ? 'absolute right-3 top-3 grid h-11 w-11 place-items-center rounded-full bg-black/70 text-white hover:bg-black focus-visible:ring-2 focus-visible:ring-white'
                  : 'absolute inset-0 flex items-center justify-center bg-black/10 text-white transition-colors hover:bg-black/25 focus-visible:outline focus-visible:-outline-offset-4 focus-visible:outline-white'}
              >
                {preview === 'playing' ? <X aria-hidden="true" size={20} /> : (
                  <span className="grid h-14 w-14 place-items-center rounded-full bg-black/65 ring-1 ring-white/60">
                    <Play aria-hidden="true" size={23} className="ml-0.5" fill="currentColor" />
                  </span>
                )}
              </button>
            </div>
          </div>
        )}

        <div className="min-w-0 p-5 sm:p-7">
          <h2 id="result-title" ref={heading} tabIndex={-1} className="break-words text-xl font-bold leading-snug text-slate-900 outline-none">
            {title}
          </h2>
          {preview === 'error' && (
            <p role="status" className="mt-2 text-sm text-slate-600">The preview couldn’t load. You can still try downloading the video.</p>
          )}

          {bestVideo ? (
            <a
              href={videoDownloadHref(bestVideo)}
              download
              target="_blank"
              rel="noopener noreferrer"
              aria-disabled={isAudioBusy}
              onClick={startVideoDownload}
              className="mt-5 flex min-h-[52px] items-center gap-3 rounded-xl bg-slate-900 px-4 py-2.5 font-semibold text-white shadow-md transition-colors hover:bg-slate-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-slate-900 aria-disabled:opacity-60"
            >
              <Download aria-hidden="true" size={20} className="shrink-0" />
              <span className="flex min-w-0 flex-wrap items-baseline gap-x-2">
                <span>Download MP4</span>
                <span className="text-sm font-medium text-slate-300">{optionDetails(bestVideo)}</span>
              </span>
            </a>
          ) : audio ? (
            <Button type="button" fullWidth isLoading={isAudioBusy} onClick={startAudioDownload} className="mt-5">
              Download MP3
            </Button>
          ) : (
            <p className="mt-3 text-sm text-slate-600">This post has no downloadable media.</p>
          )}

          {bestVideo && (otherVideos.length > 0 || audio) && (
            <details className="group mt-3 rounded-xl border border-slate-200">
              <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-3 rounded-xl px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 focus-visible:outline-slate-900 [&::-webkit-details-marker]:hidden">
                More formats
                <ChevronDown aria-hidden="true" size={16} className="transition-transform group-open:rotate-180" />
              </summary>
              <ul className="space-y-1 border-t border-slate-100 p-2">
                {otherVideos.map(option => (
                  <li key={option.quality}>
                    <a
                      href={videoDownloadHref(option)}
                      download
                      target="_blank"
                      rel="noopener noreferrer"
                      aria-disabled={isAudioBusy}
                      onClick={startVideoDownload}
                      className="flex min-h-11 items-center gap-2 rounded-lg px-2 py-1.5 text-sm text-slate-800 hover:bg-slate-100 focus-visible:outline-slate-900 aria-disabled:opacity-60"
                    >
                      <Video aria-hidden="true" size={16} />
                      Download MP4 <span className="text-slate-500">{optionDetails(option)}</span>
                    </a>
                  </li>
                ))}
                {audio && (
                  <li>
                    <button
                      type="button"
                      disabled={isAudioBusy}
                      onClick={startAudioDownload}
                      className="flex min-h-11 w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-sm text-slate-800 hover:bg-slate-100 focus-visible:outline-slate-900 disabled:opacity-60"
                    >
                      <Music aria-hidden="true" size={16} />
                      Download MP3 <span className="text-slate-500">{audio.quality}</span>
                    </button>
                  </li>
                )}
              </ul>
            </details>
          )}

          {downloadStatus === 'audio-error' ? (
            <div role="alert" className="mt-3 flex flex-wrap items-center justify-between gap-x-2 rounded-lg bg-red-50 px-3 py-1 text-sm text-red-800">
              <p>{downloadMessages[downloadStatus]}</p>
              <button type="button" onClick={startAudioDownload} className="min-h-11 font-semibold underline underline-offset-2">
                Retry MP3
              </button>
            </div>
          ) : (
            <p role="status" className={downloadStatus === 'idle' ? 'sr-only' : 'mt-3 text-sm text-slate-600'}>
              {downloadMessages[downloadStatus]}
            </p>
          )}

          <button
            type="button"
            onClick={onReset}
            className="mt-3 inline-flex min-h-11 items-center gap-2 rounded-lg text-sm font-medium text-slate-600 hover:text-slate-900 focus-visible:outline-slate-900"
          >
            <ArrowLeft aria-hidden="true" size={16} />
            Paste another link
          </button>
        </div>
      </div>
    </section>
  );
}
