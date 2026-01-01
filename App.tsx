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
  Menu,
  X as XIcon
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
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [isMobile, setIsMobile] = useState(false);

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

  // Detect mobile screen size
  useEffect(() => {
    const checkMobile = () => setIsMobile(window.innerWidth < 640);
    checkMobile();
    window.addEventListener('resize', checkMobile);
    return () => window.removeEventListener('resize', checkMobile);
  }, []);

  // Close mobile menu when clicking outside
  useEffect(() => {
    if (!mobileMenuOpen) return;
    const handleClickOutside = (e: MouseEvent) => {
      const target = e.target as HTMLElement;
      if (!target.closest('header')) {
        setMobileMenuOpen(false);
      }
    };
    document.addEventListener('click', handleClickOutside);
    return () => document.removeEventListener('click', handleClickOutside);
  }, [mobileMenuOpen]);

  const handleLogoClick = () => {
    if (showLogoAnimation) return;
    setShowLogoAnimation(true);
  };

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col pb-safe">
      {showLogoAnimation && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-white/90 backdrop-blur-md">
          <div className="flex flex-col items-center gap-4">
            <Lottie animationData={xstreamAnimation} loop={false} style={{ width: 240, height: 240 }} />
            <p className="text-slate-600 text-sm font-medium">Refreshing your XStream experience...</p>
          </div>
        </div>
      )}

      {/* Header */}
      <header className="py-4 sm:py-6 px-4 sm:px-6 md:px-12 flex justify-between items-center max-w-7xl mx-auto w-full relative pt-safe">
        <button
          type="button"
          onClick={handleLogoClick}
          className="flex items-center space-x-2 focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-slate-400 rounded-lg px-1 py-1 transition min-h-[44px]"
        >
          <div className="w-8 h-8 bg-slate-900 rounded-lg flex items-center justify-center">
            <Zap className="text-white w-5 h-5" fill="currentColor" />
          </div>
          <span className="text-lg sm:text-xl font-bold tracking-tight text-slate-900">XStream</span>
        </button>
        
        {/* Desktop Navigation */}
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
        </div>

        {/* Mobile Menu Button */}
        <button
          type="button"
          onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
          className="md:hidden p-2 text-slate-600 hover:text-slate-900 transition-colors min-h-[44px] min-w-[44px] flex items-center justify-center"
          aria-label="Toggle menu"
        >
          {mobileMenuOpen ? <XIcon size={24} /> : <Menu size={24} />}
        </button>

        {/* Mobile Menu */}
        {mobileMenuOpen && (
          <div className="absolute top-full left-0 right-0 mt-2 mx-4 bg-white rounded-2xl shadow-xl border border-slate-200 py-4 z-50 md:hidden">
            <nav className="flex flex-col space-y-1 px-4">
              <a 
                href="#how-to-use" 
                className="px-4 py-3 text-slate-600 hover:text-slate-900 hover:bg-slate-50 rounded-lg transition-colors font-medium"
                onClick={() => setMobileMenuOpen(false)}
              >
                How to use
              </a>
              <a 
                href="#faqs" 
                className="px-4 py-3 text-slate-600 hover:text-slate-900 hover:bg-slate-50 rounded-lg transition-colors font-medium"
                onClick={() => setMobileMenuOpen(false)}
              >
                FAQ
              </a>
              <button
                type="button"
                onClick={() => {
                  alert('Sorry Maamey innum vidala');
                  setMobileMenuOpen(false);
                }}
                className="px-4 py-3 text-left text-slate-600 hover:text-slate-900 hover:bg-slate-50 rounded-lg transition-colors font-medium"
              >
                API
              </button>
            </nav>
          </div>
        )}
      </header>

      {/* Main Content */}
      <main className="flex-grow flex flex-col items-center px-4 sm:px-6 lg:px-8 relative">
        
        {/* Background Decoration */}
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-full h-[500px] bg-gradient-to-b from-slate-200/50 to-transparent -z-10 blur-3xl opacity-50 pointer-events-none" />

        <div className="w-full max-w-3xl mx-auto pt-8 sm:pt-12 pb-12 sm:pb-20 text-center z-10">
          
          {status === 'idle' || status === 'loading' || status === 'error' ? (
            <>
              <div className="mb-8 sm:mb-10 space-y-3 sm:space-y-4 px-2">
                <h1 className="text-3xl sm:text-4xl md:text-5xl lg:text-6xl font-extrabold text-slate-900 tracking-tight leading-tight">
                  Download X Videos <br />
                  <span className="text-transparent bg-clip-text bg-gradient-to-r from-slate-700 to-slate-400">
                    Simple. Fast. Free.
                  </span>
                </h1>
                <p className="text-base sm:text-lg text-slate-600 max-w-2xl mx-auto px-2">
                  Save videos and GIFs from Twitter (X) in high quality MP4 and MP3 formats directly to your device. No registration required.
                </p>
              </div>

              <div className="w-full max-w-2xl mx-auto px-2">
                <form onSubmit={handleFetch} className="relative group">
                  <div className="absolute inset-0 bg-gradient-to-r from-slate-200 to-slate-300 rounded-2xl blur transition duration-500 opacity-25 group-hover:opacity-50 pointer-events-none"></div>
                  <div className="relative bg-white p-2 rounded-2xl shadow-xl ring-1 ring-slate-900/5 flex flex-col sm:flex-row items-stretch sm:items-center gap-2 sm:gap-3">
                    <div className="flex items-center gap-2 sm:gap-3 flex-1">
                      <div className="pl-3 sm:pl-4 text-slate-400 flex-shrink-0">
                        <LinkIcon size={20} />
                      </div>
                      <input
                        type="text"
                        value={url}
                        onChange={(e) => setUrl(e.target.value)}
                        placeholder={isMobile ? "Paste tweet link..." : "Paste tweet link here (e.g. https://x.com/...)"}
                        className="flex-grow bg-transparent border-none focus:ring-0 text-slate-900 placeholder-slate-400 h-12 sm:h-14 px-2 sm:px-4 text-base sm:text-lg"
                        disabled={status === 'loading'}
                      />
                    </div>
                    <div className="flex gap-2 sm:gap-3">
                      <button
                        type="button"
                        onClick={handlePaste}
                        className="sm:hidden flex items-center justify-center px-4 py-2.5 text-sm font-semibold text-slate-500 bg-slate-100 rounded-lg hover:bg-slate-200 flex-shrink-0 transition-colors min-h-[48px] min-w-[80px]"
                      >
                        Paste
                      </button>
                      <button
                        type="button"
                        onClick={handlePaste}
                        className="hidden sm:flex items-center px-3 py-1.5 text-xs font-semibold text-slate-500 bg-slate-100 rounded-lg hover:bg-slate-200 flex-shrink-0 transition-colors min-h-[44px]"
                      >
                        Paste
                      </button>
                      <Button 
                        type="submit" 
                        isLoading={status === 'loading'}
                        className="h-12 sm:h-12 px-6 sm:px-8 rounded-xl text-base flex-1 sm:flex-shrink-0 min-w-[120px] min-h-[48px]"
                      >
                        Download
                      </Button>
                    </div>
                  </div>
                  
                </form>

                {status === 'loading' && (
                  <div className="mt-4 text-center">
                    <p className="text-sm text-slate-500">Processing your link...</p>
                  </div>
                )}

                {status === 'error' && (
                  <div className="mt-4 p-4 bg-red-50 text-red-600 rounded-xl border border-red-100 flex items-center animate-in slide-in-from-top-2">
                    <span className="mr-2">⚠️</span> 
                    <span className="text-sm sm:text-base">{errorMessage}</span>
                  </div>
                )}
              </div>

              {/* Feature Highlights */}
              <div className="mt-12 sm:mt-16 md:mt-24 grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4 sm:gap-6 md:gap-8 text-left px-2">
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
              <div id="how-to-use" className="mt-12 sm:mt-16 bg-white border border-slate-100 rounded-2xl sm:rounded-3xl p-6 sm:p-8 shadow-sm scroll-mt-24 mx-2 sm:mx-0">
                <div className="flex items-center justify-between flex-wrap gap-4 mb-6">
                  <div className="text-left w-full sm:w-auto">
                    <p className="text-xs font-semibold uppercase tracking-[0.3em] text-slate-400">How to use</p>
                    <h3 className="text-xl sm:text-2xl md:text-3xl font-bold text-slate-900">3 easy steps to download</h3>
                  </div>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4 sm:gap-6">
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
        <div className="max-w-5xl mx-auto px-4 sm:px-6 py-12 sm:py-16">
          <div className="flex items-center gap-3 mb-6">
            <HelpCircle className="text-slate-500" size={20} />
            <p className="text-xs font-semibold uppercase tracking-[0.3em] text-slate-400">Support</p>
          </div>
          <h3 className="text-2xl sm:text-3xl font-bold text-slate-900 mb-6">FAQs & Supported Platforms</h3>
          <div className="space-y-4">
            {faqs.map((item) => (
              <details key={item.question} className="group border border-slate-200 rounded-xl sm:rounded-2xl p-4 sm:p-5 transition-colors">
                <summary className="flex items-center justify-between cursor-pointer text-left text-slate-900 font-semibold text-base sm:text-lg min-h-[44px] items-center">
                  <span className="flex-1 pr-4">{item.question}</span>
                  <span className="text-slate-400 text-xl group-open:hidden flex-shrink-0">+</span>
                  <span className="text-slate-400 text-xl hidden group-open:inline flex-shrink-0">−</span>
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
      <footer className="py-6 sm:py-8 text-center text-slate-400 text-xs sm:text-sm border-t border-slate-200 bg-white pb-safe">
        <div className="max-w-7xl mx-auto px-4 sm:px-6">
          <p>&copy; {new Date().getFullYear()} XStream Downloader. Not affiliated with X Corp.</p>
        </div>
      </footer>
    </div>
  );
}

export default App;