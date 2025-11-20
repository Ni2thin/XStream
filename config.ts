const normalize = (url: string) => url.replace(/\/$/, '');

export const getApiBaseUrl = () => {
  const envBase = import.meta.env.VITE_API_BASE_URL?.trim();
  if (envBase) {
    return normalize(envBase);
  }

  if (typeof window !== 'undefined') {
    const origin = window.location.origin;
    if (!origin.includes('localhost')) {
      return `${normalize(origin)}/api`;
    }
  }

  return 'http://localhost:8000';
};

export const API_BASE_URL = getApiBaseUrl();

