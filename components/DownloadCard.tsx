import React, { useState, useRef } from 'react';
import { VideoMetadata, DownloadOption } from '../types';
import { Video, Music, Play, X } from 'lucide-react';
import { getApiBaseUrl } from '../config';

interface DownloadCardProps {
  data: VideoMetadata;
  onReset: () => void;
}

export const DownloadCard: React.FC<DownloadCardProps> = ({ data, onReset }) => {
  const [downloadingId, setDownloadingId] = useState<string | null>(null);
  const [isPreviewing, setIsPreviewing] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);

  const hasOptions = Array.isArray(data.options) && data.options.length > 0;
  if (!hasOptions) {
    return (
      <div className="w-full max-w-xl bg-white rounded-3xl shadow-md border border-slate-200 p-8 text-center">
        <p className="text-lg font-semibold text-slate-900 mb-2">No download links available</p>
        <p className="text-sm text-slate-500">
          We couldn’t find any downloadable media for this tweet. It might be private, deleted, or hosted elsewhere.
        </p>
        <button
          onClick={onReset}
          className="mt-6 inline-flex items-center justify-center px-5 py-2.5 rounded-full bg-slate-900 text-white font-medium hover:bg-slate-800 transition-colors"
        >
          Try another link
        </button>
      </div>
    );
  }

  // Get the first video URL for preview (highest quality, skip MP3 options)
  const previewOption = data.options.find(opt => !opt.url.startsWith('mp3:'));
  const previewUrl = previewOption?.url || (data as any).previewUrl || '';
  const thumbnailUrl = (data as any).thumbnailUrl || '';
  const duration = (data as any).duration || '';
  const author = (data as any).author || 'Twitter User';
  const avatarUrl = (data as any).avatarUrl || '';
  const aspectRatio = (data as any).aspectRatio || '16:9';

  const handleDownload = async (option: DownloadOption) => {
    if (!option.url) {
      alert(`No download URL available for ${option.quality}`);
      return;
    }

    setDownloadingId(option.quality);
    
    try {
      const isMp3 = option.url.startsWith('mp3:');
      const fileExtension = isMp3 ? 'mp3' : 'mp4';
      const fileName = `${data.title.replace(/[^a-z0-9]/gi, '_').toLowerCase()}_${option.quality}.${fileExtension}`;
      
      // Use backend proxy to handle CORS and ensure direct download
      const apiBase = getApiBaseUrl();
      const proxyUrl = `${apiBase}/api/download?url=${encodeURIComponent(option.url)}`;
      
      const response = await fetch(proxyUrl, {
        method: 'GET',
      });
      
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || 'Download failed');
      }
      
      const blob = await response.blob();
      const blobUrl = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = blobUrl;
      link.download = fileName;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(blobUrl);
      setDownloadingId(null);
    } catch (error: any) {
      console.error('Download error:', error);
      // For MP3, show a more helpful error message
      if (option.url.startsWith('mp3:')) {
        alert('MP3 conversion failed. This may take a moment. Please try again.');
      } else {
        // Fallback: try direct link
        try {
          const link = document.createElement('a');
          link.href = option.url;
          link.download = `${data.title.replace(/[^a-z0-9]/gi, '_').toLowerCase()}_${option.quality}.mp4`;
          link.target = '_blank';
          link.rel = 'noopener noreferrer';
          document.body.appendChild(link);
          link.click();
          document.body.removeChild(link);
        } catch (fallbackError) {
          console.error('Fallback download error:', fallbackError);
          alert('Download failed. Please try right-clicking on the video and selecting "Save video as..."');
        }
      }
      setDownloadingId(null);
    }
  };

  const togglePreview = () => {
    setIsPreviewing(!isPreviewing);
  };

  return (
    <div className="w-full max-w-4xl bg-white rounded-3xl shadow-xl overflow-hidden border border-slate-100 animate-in fade-in slide-in-from-bottom-4 duration-500">
      <div className="flex flex-col lg:flex-row">
        {/* Preview Section */}
        <div className={`relative bg-slate-900 flex items-center justify-center overflow-hidden ${aspectRatio === '9:16' ? 'lg:w-1/3 h-96 lg:h-auto' : 'lg:w-1/2 h-64 lg:h-auto'}`}>
            
            {isPreviewing && previewUrl ? (
              <div className="absolute inset-0 w-full h-full bg-black animate-in fade-in duration-300 z-20">
                <video 
                  ref={videoRef}
                  src={previewUrl} 
                  className="w-full h-full object-contain"
                  controls
                  autoPlay
                  playsInline
                  crossOrigin="anonymous"
                />
                <button 
                  onClick={togglePreview}
                  className="absolute top-4 right-4 p-2 bg-black/50 backdrop-blur-md rounded-full text-white/80 hover:text-white hover:bg-black/70 transition-all z-10"
                  aria-label="Close Preview"
                >
                  <X size={20} />
                </button>
              </div>
            ) : previewUrl ? (
              <>
                <video 
                  src={previewUrl}
                  className="w-full h-full object-cover opacity-90"
                  muted
                  playsInline
                  loop
                  crossOrigin="anonymous"
                />
                <div 
                  className="absolute inset-0 flex items-center justify-center cursor-pointer group bg-black/20"
                  onClick={togglePreview}
                >
                  <div className="w-16 h-16 rounded-full bg-white/20 backdrop-blur-sm flex items-center justify-center ring-1 ring-white/50 shadow-2xl group-hover:scale-110 transition-transform duration-300">
                    <Play className="w-8 h-8 text-white ml-1" fill="currentColor" />
                  </div>
                </div>
                {duration && (
                  <div className="absolute bottom-4 right-4 px-3 py-1 bg-black/60 backdrop-blur-md rounded-full text-white text-xs font-medium pointer-events-none">
                    {duration}
                  </div>
                )}
              </>
            ) : (
              <div className="w-full h-full flex items-center justify-center text-slate-400">
                <Video size={48} />
              </div>
            )}
        </div>

        {/* Content Section */}
        <div className="p-8 lg:w-2/3 flex flex-col">
          {avatarUrl && (
            <div className="flex items-center mb-4">
              <img src={avatarUrl} alt="Author" className="w-10 h-10 rounded-full bg-slate-100" />
              <div className="ml-3">
                <p className="text-sm font-bold text-slate-900">{author}</p>
                <p className="text-xs text-slate-500">Twitter / X</p>
              </div>
            </div>
          )}

          <h2 className="text-xl font-bold text-slate-900 mb-6 leading-snug line-clamp-2">
            {data.title}
          </h2>

          <div className="space-y-3 flex-grow">
            <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">Available Formats</h3>
            
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {data.options.map((option, index) => {
                const optionId = (option as any).id || option.quality || `option-${index}`;
                const isBest = index === 0 && !option.url.startsWith('mp3:'); // First video option is highest quality
                const isMp3 = option.url.startsWith('mp3:');
                const extension = isMp3 ? 'mp3' : ((option as any).extension || 'mp4');
                const size = (option as any).size || '';
                
                return (
                  <button
                    key={optionId}
                    onClick={() => handleDownload(option)}
                    disabled={!!downloadingId}
                    className={`
                      relative group flex items-center justify-between gap-4 p-4 rounded-2xl border text-left transition-all duration-200
                      ${isMp3
                        ? 'border-purple-500/30 bg-purple-50/50 hover:bg-purple-50 hover:border-purple-500'
                        : isBest 
                        ? 'border-blue-500/30 bg-blue-50/50 hover:bg-blue-50 hover:border-blue-500' 
                        : 'border-slate-200 hover:border-slate-400 hover:bg-slate-50'
                      }
                      ${downloadingId ? 'opacity-75 cursor-not-allowed' : 'cursor-pointer'}
                    `}
                  >
                    <div className="flex items-center gap-4">
                      <div className={`
                        w-12 h-12 rounded-2xl flex items-center justify-center
                        ${extension === 'mp3' ? 'bg-purple-100 text-purple-600' : 'bg-slate-100 text-slate-700'}
                      `}>
                        {extension === 'mp3' ? <Music size={22} /> : <Video size={22} />}
                      </div>
                      <div>
                        <div className="font-bold text-slate-900 flex items-center gap-2 text-lg">
                          {option.quality}
                          {isMp3 && (
                            <span className="px-2 py-0.5 bg-purple-600 text-white text-[10px] font-bold uppercase rounded-full tracking-wide">
                              Audio
                            </span>
                          )}
                          {isBest && !isMp3 && (
                            <span className="px-2 py-0.5 bg-blue-600 text-white text-[10px] font-bold uppercase rounded-full tracking-wide">
                              Best
                            </span>
                          )}
                        </div>
                        <div className="text-xs text-slate-500 uppercase">
                          {extension.toUpperCase()}{size ? ` • ${size}` : ''}
                        </div>
                      </div>
                    </div>
                    
                  </button>
                );
              })}
            </div>
          </div>

          <div className="mt-8 pt-6 border-t border-slate-100 flex justify-between items-center">
             <button 
               onClick={onReset}
               className="text-sm text-slate-500 hover:text-slate-900 font-medium transition-colors"
             >
               ← Paste another link
             </button>
          </div>
        </div>
      </div>
    </div>
  );
};