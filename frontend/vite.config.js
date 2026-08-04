import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig(({ command, mode }) => {
  const env = loadEnv(mode, process.cwd(), '')

  // VITE_API_BASE_URL is baked into the bundle at build time (see src/api/client.js) —
  // if it's unset, every fetch() silently targets "undefined/api/..." instead of
  // failing loudly, so a production build without it must not be allowed to succeed.
  if (command === 'build' && !env.VITE_API_BASE_URL) {
    throw new Error(
      'VITE_API_BASE_URL is not set. Set it in your hosting platform\'s environment ' +
      'variables (Vercel/Netlify/etc.) before building for production — see backend/README-DEPLOY.md.',
    )
  }

  return {
    plugins: [react(), tailwindcss()],
    server: {
      port: 5173,
    },
  }
})
