/** @type {import('next').NextConfig} */

// When set, scopes the app under a subpath (e.g., `/spm-calculator` when
// the app is reverse-proxied behind policyengine.org/spm-calculator).
// Leave unset for the standalone deployment at spm-calculator.vercel.app.
const basePath = process.env.NEXT_PUBLIC_BASE_PATH ?? "";

const nextConfig = {
  output: "export",
  basePath: basePath || undefined,
  assetPrefix: basePath || undefined,
  env: {
    NEXT_PUBLIC_BASE_PATH: basePath,
  },
  // Next.js 16 trailingSlash avoids double-redirect issues when served
  // behind a reverse-proxy rewrite.
  trailingSlash: true,
};

export default nextConfig;
