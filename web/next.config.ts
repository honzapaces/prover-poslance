import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  images: {
    remotePatterns: [
      {
        protocol: "https",
        hostname: "www.psp.cz",
        pathname: "/eknih/cdrom/web/poslanci/**",
      },
    ],
  },
};

export default nextConfig;
