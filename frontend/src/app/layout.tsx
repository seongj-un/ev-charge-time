import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";

import { SessionProvider } from "@/components/auth/SessionProvider";
import { AppShell } from "@/components/shell/AppShell";
import { SERVICE_NAME } from "@/components/shell/nav";

import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: `${SERVICE_NAME} · 언제 충전하면 가장 쌀까요?`,
    template: `%s · ${SERVICE_NAME}`,
  },
  description:
    "2026년 계절·시간대별 전기요금 개편을 반영해 가장 싸게 충전할 수 있는 시간을 찾아드립니다.",
  applicationName: SERVICE_NAME,
  manifest: "/manifest.webmanifest",
};

export const viewport: Viewport = {
  themeColor: "#F1F0EB",
  // 요금 표와 차트를 손가락으로 키워 볼 수 있어야 한다. 확대를 막지 않는다.
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="ko">
      <body className="antialiased">
        <SessionProvider>
          <AppShell>{children}</AppShell>
        </SessionProvider>
      </body>
    </html>
  );
}
