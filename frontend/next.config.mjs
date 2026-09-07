/** @type {import('next').NextConfig} */
<<<<<<< HEAD

const nextConfig = {
  output: "standalone",
  reactStrictMode: true,

  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: "http://backend:8000/api/:path*",
      },
    ];
  },
};

export default nextConfig;
=======
const nextConfig = {
  output: "standalone",
  reactStrictMode: true,
};
export default nextConfig;
>>>>>>> 6727b112c8de5cc5eeb838298c25b57edf006ee5
