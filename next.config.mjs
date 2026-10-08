/** @type {import('next').NextConfig} */
const nextConfig = (phase) => ({
  // Builds must not overwrite a running development server's route manifests.
  distDir: phase === "phase-development-server" ? ".next-dev" : ".next",
  transpilePackages: ["wavesurfer.js"],
});

export default nextConfig;
