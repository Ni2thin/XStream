const normalize = (url: string) => url.replace(/\/$/, '');

export const getApiBaseUrl = () => {
  // Priority 1: Use environment variable (set in Vercel/Render)
  const envBase = import.meta.env.VITE_API_BASE_URL?.trim();
  if (envBase) {
    return normalize(envBase);
  }

  // Priority 2: In production (non-localhost), check if API is on same origin
  if (typeof window !== 'undefined') {
    const origin = window.location.origin;
    if (!origin.includes('localhost') && !origin.includes('127.0.0.1')) {
      // In production, you should set VITE_API_BASE_URL
      // This fallback assumes API is on same origin (not recommended)
      console.warn('VITE_API_BASE_URL not set. Please configure it in your deployment environment.');
      return `${normalize(origin)}/api`;
    }
  }

  // Priority 3: Default to localhost for development
  return 'http://localhost:8000';
};

export const API_BASE_URL = getApiBaseUrl();

