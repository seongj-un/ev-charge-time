import type { Metadata } from "next";

import { PageBody, PageHero } from "@/components/shell/AppShell";
import { ButtonLink } from "@/components/ui/Button";

export const metadata: Metadata = {
  title: "페이지를 찾을 수 없어요",
};

/**
 * 없는 주소. Next 기본 404는 영어 한 줄("This page could not be found.")이라
 * 한국어 앱 안에서 고장 난 화면처럼 보인다. 갈 곳 두 개를 바로 준다.
 */
export default function NotFound() {
  return (
    <>
      <PageHero
        eyebrow="404"
        title="페이지를 찾을 수 없어요"
        description="주소가 바뀌었거나 잘못 입력된 것 같아요. 아래에서 바로 이어 갈 수 있어요."
      />
      <PageBody>
        <div className="flex flex-col gap-3 sm:flex-row">
          <ButtonLink href="/recommend" size="lg">
            충전 시간 추천받기
          </ButtonLink>
          <ButtonLink href="/" variant="outline" size="lg">
            홈으로
          </ButtonLink>
        </div>
      </PageBody>
    </>
  );
}
