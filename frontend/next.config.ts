import type { NextConfig } from "next";

// Static export: the build emits plain HTML/JS/CSS into `out/`, served by
// FastAPI (or any web server). No Node.js process runs in production.
const nextConfig: NextConfig = {
  output: "export",
  trailingSlash: true,
  poweredByHeader: false,
  reactStrictMode: true,
  images: { unoptimized: true },
};

export default nextConfig;
