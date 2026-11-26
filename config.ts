export const getApiBaseUrl = () => {
  const configured = import.meta.env.VITE_API_BASE_URL?.trim();
  if (configured) {
    if (configured === '/') return window.location.origin;
    try {
      const url = new URL(configured);
      if (
        (url.protocol === 'http:' || url.protocol === 'https:') &&
        !url.username && !url.password && !url.search && !url.hash &&
        /^\/+$/.test(url.pathname)
      ) {
        return url.origin;
      }
    } catch {
      // The deployment error below also covers malformed settings.
    }
  } else if (import.meta.env.DEV) {
    return 'http://localhost:8000';
  }

  throw new Error('The downloader is unavailable because its API address is not configured. Please try again later.');
};

