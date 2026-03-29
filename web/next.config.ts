import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  images: {
    remotePatterns: [
      {
        protocol: "https",
        hostname: "www.psp.cz",
        pathname: "/eknih/cdrom/**",
      },
    ],
  },
};

export default nextConfig;
