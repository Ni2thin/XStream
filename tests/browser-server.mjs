import { readFileSync } from 'node:fs';
import { createServer } from 'vite';

const origin = 'http://127.0.0.1:4173';
const media = readFileSync(new URL('./fixtures/preview.mp4', import.meta.url));
const server = await createServer({
  server: { host: '127.0.0.1', port: 4173, strictPort: true },
  plugins: [{
    name: 'xstream-native-download-fixture',
    configureServer({ middlewares }) {
      middlewares.use((request, response, next) => {
        const url = new URL(request.url ?? '/', origin);
        if (url.pathname !== '/api/download' || url.searchParams.get('url')?.startsWith('mp3:')) {
          return next();
        }

        // WebKit's native download manager requires an HTTP response for an attachment.
        const title = (url.searchParams.get('filename') || 'video').replace(/[^a-zA-Z0-9 ._-]/g, '_');
        response.writeHead(200, {
          'Content-Type': 'video/mp4',
          'Content-Disposition': 'attachment; filename="' + title + '.mp4"',
          'Content-Length': media.length,
        });
        response.end(media);
      });
    },
  }],
});

await server.listen();
