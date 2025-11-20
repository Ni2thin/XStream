import React, { useEffect, useState } from 'react';
import { fetchTweetMetadata } from './services/api';
import { VideoMetadata, ApiError } from './types';
import { Button } from './components/Button';
import { DownloadCard } from './components/DownloadCard';
import { 
  Link as LinkIcon, 
  Zap, 
  Shield, 
  Smartphone,
  ClipboardList,
  MousePointerClick,
  Download,
  HelpCircle,
  Globe
} from 'lucide-react';
import Lottie from 'lottie-react';
import xstreamAnimation from './assets/xstream.json';

const faqs = [
  {
    question: 'Does this work on iPhone and Android?',
    answer: 'Yes. XStream is a responsive web app that works in Safari, Chrome, Edge, and Firefox on iPhone, Android, tablets, and desktop.'
  },
  {
    question: 'Can I download videos from private accounts?',
    answer: 'No. If a tweet is protected or the account is private, Twitter/X prevents tools like ours from accessing the content.'
  },
  {
    question: 'What if a tweet was deleted?',
    answer: 'Deleted or removed tweets cannot be downloaded. Please make sure the tweet is still visible before pasting the link.'
  },
  {
    question: 'Why do some links fail?',
    answer: 'Occasionally X/Twitter may rate-limit requests or the video might be region locked. Trying again in a few minutes usually resolves it.'
  }
];

function App() {
  const [url, setUrl] = useState('');
  const [status, setStatus] = useState<'idle' | 'loading' | 'success' | 'error'>('idle');
  const [videoData, setVideoData] = useState<VideoMetadata | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [showLogoAnimation, setShowLogoAnimation] = useState(false);
  const [showSupportedMenu, setShowSupportedMenu] = useState(false);

  const handleFetch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!url.trim()) return;

    setStatus('loading');
    setErrorMessage(null);

    try {
      const data = await fetchTweetMetadata(url);
      setVideoData(data);
      setStatus('success');
    } catch (err: any) {
      setStatus('error');
      setErrorMessage(err.message || 'Failed to fetch video');
    }
  };

  const handlePaste = async () => {
    try {
      const text = await navigator.clipboard.readText();
      setUrl(text);
    } catch (err) {
      console.error('Failed to read clipboard');
    }
  };

  const reset = () => {
    setUrl('');
    setStatus('idle');
    setVideoData(null);
  };

  useEffect(() => {
    if (!showLogoAnimation) return;
    const timeout = window.setTimeout(() => {
      window.location.reload();
    }, 2200);
    return () => window.clearTimeout(timeout);
  }, [showLogoAnimation]);

  const handleLogoClick = () => {
    if (showLogoAnimation) return;
    setShowLogoAnimation(true);
  };

  const supportedPlatforms = [
    'X / Twitter (Web & App)',
    'iPhone & iPad (Safari, Chrome)',
    'Android Phones & Tablets',
    'Mac & Windows Desktop',
    'Chromebook & Linux'
  ];

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col">
      {showLogoAnimation && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-white/90 backdrop-blur-md">
          <div className="flex flex-col items-center gap-4">
            <Lottie animationData={xstreamAnimation} loop={false} style={{ width: 240, height: 240 }} />
            <p className="text-slate-600 text-sm font-medium">Refreshing your XStream experience...</p>
          </div>
        </div>
      )}

      {/* Header */}
      <header className="py-6 px-6 md:px-12 flex justify-between items-center max-w-7xl mx-auto w-full">
        <button
          type="button"
          onClick={handleLogoClick}
          className="flex items-center space-x-2 focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-slate-400 rounded-lg px-1 py-1 transition"
        >
          <div className="w-8 h-8 bg-slate-900 rounded-lg flex items-center justify-center">
            <Zap className="text-white w-5 h-5" fill="currentColor" />
          </div>
          <span className="text-xl font-bold tracking-tight text-slate-900">XStream</span>
        </button>
        <div className="hidden md:flex items-center space-x-6 text-sm font-medium text-slate-500">
          <nav className="flex space-x-6">
            <a href="#how-to-use" className="hover:text-slate-900 transition-colors">How to use</a>
            <a href="#faqs" className="hover:text-slate-900 transition-colors">FAQ</a>
            <button
              type="button"
              onClick={() => alert('Sorry Maamey innum vidala')}
              className="hover:text-slate-900 transition-colors focus:outline-none"
            >
              API
            </button>
          </nav>
          <div 
            className="relative"
            onMouseLeave={() => setShowSupportedMenu(false)}
          >
            <button
              type="button"
              onClick={() => setShowSupportedMenu((prev) => !prev)}
              className="flex items-center gap-2 px-3 py-1.5 rounded-full border border-slate-200 text-slate-600 hover:text-slate-900 hover:border-slate-900 transition-colors"
            >
              <Globe size={16} />
              Supported Sites
            </button>
            {showSupportedMenu && (
              <div className="absolute right-0 mt-2 w-64 rounded-2xl border border-slate-100 bg-white shadow-lg shadow-slate-900/5 p-4 text-left space-y-2 z-20">
                <p className="text-xs font-semibold uppercase tracking-[0.25em] text-slate-400">
                  Works Great On
                </p>
                <ul className="mt-2 space-y-1 text-sm text-slate-600">
                  {supportedPlatforms.map((platform) => (
                    <li 
                      key={platform}
                      className="flex items-center gap-2 py-1"
                    >
                      <span className="w-2 h-2 rounded-full bg-slate-300" />
                      <span>{platform}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-grow flex flex-col items-center px-4 sm:px-6 relative">
        
        {/* Background Decoration */}
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-full h-[500px] bg-gradient-to-b from-slate-200/50 to-transparent -z-10 blur-3xl opacity-50 pointer-events-none" />

        <div className="w-full max-w-3xl mx-auto pt-12 pb-20 text-center z-10">
          
          {status === 'idle' || status === 'loading' || status === 'error' ? (
            <>
              <div className="mb-10 space-y-4">
                <h1 className="text-4xl md:text-6xl font-extrabold text-slate-900 tracking-tight leading-tight">
                  Download X Videos <br />
                  <span className="text-transparent bg-clip-text bg-gradient-to-r from-slate-700 to-slate-400">
                    Simple. Fast. Free.
                  </span>
                </h1>
                <p className="text-lg text-slate-600 max-w-2xl mx-auto">
                  Save videos and GIFs from Twitter (X) in high quality MP4 and MP3 formats directly to your device. No registration required.
                </p>
              </div>

              <div className="w-full max-w-2xl mx-auto">
                <form onSubmit={handleFetch} className="relative group">
                  <div className="absolute inset-0 bg-gradient-to-r from-slate-200 to-slate-300 rounded-2xl blur transition duration-500 opacity-25 group-hover:opacity-50 pointer-events-none"></div>
                  <div className="relative bg-white p-2 rounded-2xl shadow-xl ring-1 ring-slate-900/5 flex items-center gap-3 p-2 pr-3">
                    <div className="pl-4 text-slate-400 flex-shrink-0">
                      <LinkIcon size={20} />
                    </div>
                    <input
                      type="text"
                      value={url}
                      onChange={(e) => setUrl(e.target.value)}
                      placeholder="Paste tweet link here (e.g. https://x.com/...)"
                      className="flex-grow bg-transparent border-none focus:ring-0 text-slate-900 placeholder-slate-400 h-14 px-4 text-lg"
                      disabled={status === 'loading'}
                    />
                    <button
                      type="button"
                      onClick={handlePaste}
                      className="hidden sm:flex items-center px-3 py-1.5 text-xs font-semibold text-slate-500 bg-slate-100 rounded-lg hover:bg-slate-200 flex-shrink-0 transition-colors"
                    >
                      Paste
                    </button>
                    <Button 
                      type="submit" 
                      isLoading={status === 'loading'}
                      className="h-12 px-8 rounded-xl text-base flex-shrink-0"
                    >
                      Download
                    </Button>
                  </div>
                  
                </form>

                {status === 'error' && (
                  <div className="mt-4 p-4 bg-red-50 text-red-600 rounded-xl border border-red-100 flex items-center animate-in slide-in-from-top-2">
                    <span className="mr-2">⚠️</span> {errorMessage}
                  </div>
                )}
              </div>

              {/* Feature Highlights */}
              <div className="mt-24 grid grid-cols-1 md:grid-cols-3 gap-8 text-left">
                <div className="p-6 rounded-2xl bg-white border border-slate-100 shadow-sm hover:shadow-md transition-shadow">
                  <div className="w-10 h-10 bg-blue-50 rounded-full flex items-center justify-center text-blue-600 mb-4">
                    <Zap size={20} />
                  </div>
                  <h3 className="font-bold text-slate-900 mb-2">Lightning Fast</h3>
                  <p className="text-slate-500 text-sm">Our optimized engine processes links instantly to get you your content without waiting.</p>
                </div>
                <div className="p-6 rounded-2xl bg-white border border-slate-100 shadow-sm hover:shadow-md transition-shadow">
                  <div className="w-10 h-10 bg-green-50 rounded-full flex items-center justify-center text-green-600 mb-4">
                    <Shield size={20} />
                  </div>
                  <h3 className="font-bold text-slate-900 mb-2">Secure & Private</h3>
                  <p className="text-slate-500 text-sm">We don't store your download history or videos. Your privacy is our priority.</p>
                </div>
                <div className="p-6 rounded-2xl bg-white border border-slate-100 shadow-sm hover:shadow-md transition-shadow">
                  <div className="w-10 h-10 bg-purple-50 rounded-full flex items-center justify-center text-purple-600 mb-4">
                    <Smartphone size={20} />
                  </div>
                  <h3 className="font-bold text-slate-900 mb-2">Mobile Friendly</h3>
                  <p className="text-slate-500 text-sm">Works perfectly on iPhone, Android, and tablets with a responsive design.</p>
                </div>
              </div>

              {/* How to Use */}
              <div id="how-to-use" className="mt-16 bg-white border border-slate-100 rounded-3xl p-8 shadow-sm scroll-mt-24">
                <div className="flex items-center justify-between flex-wrap gap-4 mb-6">
                  <div className="text-left">
                    <p className="text-xs font-semibold uppercase tracking-[0.3em] text-slate-400">How to use</p>
                    <h3 className="text-2xl md:text-3xl font-bold text-slate-900">3 easy steps to download</h3>
                  </div>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                  {[
                    { icon: ClipboardList, title: 'Copy the Tweet Link', text: 'Tap the share icon on the tweet and copy the link to the post you want.' },
                    { icon: MousePointerClick, title: 'Paste the Link', text: 'Paste into the input box above and hit download. No login required.' },
                    { icon: Download, title: 'Choose Quality & Save', text: 'Select the MP4 or MP3 format you need and save directly to your device.' },
                  ].map((step, idx) => (
                    <div key={step.title} className="p-6 rounded-2xl border border-slate-100 hover:border-slate-200 transition-colors text-left">
                      <div className="w-10 h-10 rounded-full bg-slate-900 text-white flex items-center justify-center mb-4">
                        <step.icon size={20} />
                      </div>
                      <p className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-1">Step {idx + 1}</p>
                      <h4 className="font-semibold text-slate-900 mb-2">{step.title}</h4>
                      <p className="text-sm text-slate-500">{step.text}</p>
                    </div>
                  ))}
                </div>
              </div>
            </>
          ) : (
            <div className="w-full flex justify-center">
              {videoData && <DownloadCard data={videoData} onReset={reset} />}
            </div>
          )}
        </div>
      </main>

      {/* FAQ Section */}
      <section id="faqs" className="bg-white border-t border-slate-200 scroll-mt-24">
        <div className="max-w-5xl mx-auto px-6 py-16">
          <div className="flex items-center gap-3 mb-6">
            <HelpCircle className="text-slate-500" />
            <p className="text-xs font-semibold uppercase tracking-[0.3em] text-slate-400">Support</p>
          </div>
          <h3 className="text-3xl font-bold text-slate-900 mb-6">FAQs & Supported Platforms</h3>
          <div className="space-y-4">
            {faqs.map((item) => (
              <details key={item.question} className="group border border-slate-200 rounded-2xl p-5 transition-colors">
                <summary className="flex items-center justify-between cursor-pointer text-left text-slate-900 font-semibold text-lg">
                  {item.question}
                  <span className="text-slate-400 group-open:hidden">+</span>
                  <span className="text-slate-400 hidden group-open:inline">−</span>
                </summary>
                <p className="mt-3 text-slate-500 text-sm leading-relaxed">
                  {item.answer}
                </p>
              </details>
            ))}
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="py-8 text-center text-slate-400 text-sm border-t border-slate-200 bg-white">
        <div className="max-w-7xl mx-auto px-6">
          <p>&copy; {new Date().getFullYear()} XStream Downloader. Not affiliated with X Corp.</p>
        </div>
      </footer>
    </div>
  );
}

export default App;