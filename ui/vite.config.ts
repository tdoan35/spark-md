import { defineConfig, type Plugin } from "vite"
import react from "@vitejs/plugin-react-swc"
import tailwindcss from "@tailwindcss/vite"
import path from "node:path"

/** drei's useGLTF configures a DRACOLoader pointing at gstatic. Our glbs are uncompressed, so
 *  the decoder URL is never fetched — but the air-gap audit greps the bundle for CDNs. Blank it. */
function stripCdnUrls(): Plugin {
  return {
    name: "sparkmd-strip-cdn",
    apply: "build",
    enforce: "post",
    renderChunk(code) {
      const out = code.replace(/https:\/\/www\.gstatic\.com\/draco\/versioned\/decoders\/[^"`']*/g, "")
      return out === code ? null : { code: out, map: null }
    },
  }
}

export default defineConfig({
  plugins: [react(), tailwindcss(), stripCdnUrls()],
  resolve: { alias: { "@": path.resolve(__dirname, "./src") } },
  server: {
    port: 5173,
    proxy: { "/api": { target: process.env.SPARKMD_UI_TARGET ?? "http://127.0.0.1:8101" } },
  },
  build: { outDir: "dist", sourcemap: false, chunkSizeWarningLimit: 1200 },
})
