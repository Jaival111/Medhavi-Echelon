/** @type {import('next').NextConfig} */
const nextConfig = {
    reactStrictMode: true,
    async rewrites() {
        const backendUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
        return [
            { source: '/auth/:path*', destination: `${backendUrl}/auth/:path*` },
            { source: '/users/:path*', destination: `${backendUrl}/users/:path*` },
            { source: '/api/:path*', destination: `${backendUrl}/api/:path*` },
            { source: '/health', destination: `${backendUrl}/health` },
        ]
    },
}

module.exports = nextConfig
