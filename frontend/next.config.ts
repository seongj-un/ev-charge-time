import type { NextConfig } from "next";

/**
 * 백엔드는 별도 포트(FastAPI)에서 돈다. 브라우저가 직접 치면 교차 출처가 되는데
 * 백엔드에 CORS 미들웨어가 없고, 인증이 httpOnly 쿠키라 교차 출처는 성가시다.
 * rewrite로 넘기면 브라우저 입장에선 동일 출처라 쿠키가 그냥 실린다.
 */
const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  /*
   * 컨테이너로 배포하려고 standalone으로 낸다. .next/standalone 안에 필요한
   * node_modules만 추려 담기므로 이미지가 작아지고, `node server.js` 한 줄로
   * 뜬다. 로컬 개발(`next dev`)에는 영향이 없다.
   */
  output: "standalone",

  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${BACKEND_URL}/api/:path*` },
      { source: "/health", destination: `${BACKEND_URL}/health` },
    ];
  },
};

export default nextConfig;
