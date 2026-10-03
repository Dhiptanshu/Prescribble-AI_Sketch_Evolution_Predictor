import { defineConfig } from "vite";

// One self-contained classic script (IIFE): <script src=".../widget/prescribble-widget.js"></script> works on any web page.
// The model (ONNX) and the WebAssembly runtime are NOT bundled: they are fetched at run time from the host that served this script.
export default defineConfig({
  build: {
    target: "es2022",
    lib: { entry: "src/index.ts", name: "PrescribbleBundle", formats: ["iife"], fileName: () => "prescribble-widget.js" },
    emptyOutDir: true,
    minify: true,
  },
  test: { environment: "jsdom", globals: true, include: ["tests/**/*.test.ts"] },
});
