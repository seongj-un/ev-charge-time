"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { useSession } from "@/components/auth/SessionProvider";
import { Button, ButtonLink } from "@/components/ui/Button";
import { Field } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";
import { ApiError } from "@/lib/api/client";
import { login } from "@/lib/api/endpoints";

/**
 * 로그인 폼 (F-11).
 *
 * 성공하면 응답이 준 User를 그대로 세션에 넘긴다. 쿠키는 httpOnly라 프론트가
 * 읽을 수 없지만, 응답 본문에 사용자가 들어 있으니 /api/me를 또 부를 이유가 없다.
 */

/*
 * 401은 백엔드가 이메일·비밀번호 중 무엇이 틀렸는지 알려주지 않는다. 가입 여부를
 * 노출하지 않으려는 의도된 설계다. 화면이 "없는 이메일입니다"처럼 나눠 말하면
 * 그 방어가 그 자리에서 무너지므로, 폼 전체 오류 한 문장으로만 보여준다.
 */
const CREDENTIALS_ERROR = "이메일 또는 비밀번호가 올바르지 않습니다.";

/*
 * 429는 연속 5회 실패 뒤 15분 잠금이다. **잠긴 동안은 비밀번호가 맞아도 429**라서
 * 401과 같은 문장을 보여주면, 맞는 비밀번호를 의심하며 계속 두드리게 된다.
 */
const LOCKED_ERROR = "로그인 실패가 많아 잠시 잠겼어요. 15분 뒤에 다시 시도해 주세요.";

const OFFLINE_ERROR = "서버에 연결하지 못했습니다. 백엔드가 실행 중인지 확인해 주세요.";

/** 서버가 거르는 것과 같은 수준의 헐거운 검사. 확정은 서버가 한다. */
const EMAIL_SHAPE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

type FieldErrors = { email?: string; password?: string };

export function LoginForm({ nextPath }: { nextPath?: string | null }) {
  const router = useRouter();
  const { status, signIn } = useSession();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  // 세션 확인이 서버에 닿지 못한 상태다. 눌러 봐야 같은 이유로 실패하므로 막는다.
  const offline = status === "unreachable";

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending || offline) return;

    const errors: FieldErrors = {};
    if (email.trim() === "") {
      errors.email = "이메일을 입력해 주세요.";
    } else if (!EMAIL_SHAPE.test(email.trim())) {
      // 백엔드도 형식을 거른다(422). 오타는 가장 잦은 실수라 왕복 없이 바로 말해 준다.
      errors.email = "이메일 형식이 올바르지 않아요.";
    }
    if (password === "") errors.password = "비밀번호를 입력해 주세요.";
    setFieldErrors(errors);
    if (errors.email || errors.password) {
      // 빈 칸 때문에 나가는 422는 실패 횟수만 쌓는다. 서버에 가기 전에 막는다.
      setFormError(null);
      return;
    }

    setPending(true);
    setFormError(null);
    try {
      const user = await login({ email: email.trim(), password });
      signIn(user);
      router.push(nextPath ?? "/me");
      // 성공하면 화면을 떠난다. pending을 풀지 않는 건 이동하는 사이에 버튼이
      // 다시 살아나 두 번째 로그인이 나가는 걸 막기 위한 것이다.
    } catch (error) {
      setFormError(loginErrorMessage(error));
      setPending(false);
    }
  }

  /*
   * 확인이 끝나기 전(loading)에는 폼을 그대로 그린다. 세션을 기다리며 폼을 감추면
   * 바로 타이핑하려던 사람이 멈칫하는데, 이 화면에 오는 사람은 대부분 로그인하지
   * 않은 사람이다. 로그인한 것으로 밝혀지면 그때 안내로 바꾼다.
   */
  if (status === "authenticated") {
    return <AlreadySignedIn />;
  }

  /*
   * min-h: 모바일에서 "로그인 없이 추천받기"를 화면 맨 아래(탭바 바로 위)에 두려고
   * 남은 높이를 채운다. 116px은 셸이 이미 쓰고 있는 여백이다 — AppShell의 pb-24(96px,
   * 탭바 자리)와 PageContainer의 pt-5(20px). 어긋나도 링크 위치만 조금 달라진다.
   */
  return (
    <section className="mx-auto flex min-h-[calc(100dvh-116px)] w-full max-w-[420px] flex-col pb-6 lg:min-h-0 lg:pt-[12vh]">
      <div className="lg:rounded-card lg:border lg:border-line lg:bg-surface lg:p-8">
        {/* 모바일은 폼이 화면을 다 덮는다. 빠져나갈 길이 없으면 막다른 길이 된다. */}
        <Link
          href="/"
          aria-label="닫기"
          className="-ml-2 mb-3 inline-flex size-10 items-center justify-center rounded-pill text-ink transition-colors hover:bg-sunken lg:hidden"
        >
          <CloseIcon />
        </Link>

        <h1 className="text-[28px] font-bold tracking-tight">로그인</h1>
        <p className="mt-2 text-sm text-ink-2">
          추천 결과를 저장하고 내 차량을 불러오려면 로그인하세요.
        </p>

        {offline ? (
          <div role="alert" className="mt-5">
            <Notice>{OFFLINE_ERROR}</Notice>
          </div>
        ) : null}

        {formError ? (
          <div role="alert" className="mt-5">
            <Notice>{formError}</Notice>
          </div>
        ) : null}

        {/* noValidate: 브라우저 기본 풍선말은 우리 오류 문장과 말투도 위치도 다르다. */}
        <form onSubmit={handleSubmit} noValidate className="mt-6 space-y-5">
          <Field
            label="이메일"
            type="email"
            autoComplete="email"
            placeholder="name@example.com"
            value={email}
            error={fieldErrors.email}
            onChange={(event) => setEmail(event.target.value)}
          />
          <Field
            label="비밀번호"
            type="password"
            autoComplete="current-password"
            value={password}
            error={fieldErrors.password}
            onChange={(event) => setPassword(event.target.value)}
          />
          <Button
            type="submit"
            variant="dark"
            size="lg"
            className="w-full"
            disabled={pending || offline}
          >
            {pending ? "로그인 중…" : "로그인"}
          </Button>
        </form>

        <p className="mt-5 text-center text-sm text-ink-2">
          계정이 없나요?{" "}
          <Link href="/signup" className="font-bold text-brand underline underline-offset-4">
            회원가입
          </Link>
        </p>
      </div>

      {/* 추천은 로그인 없이도 전부 쓸 수 있다. 그 사실을 이 화면에서 밝혀 둔다. */}
      <p className="mt-auto pt-10 text-center lg:mt-6 lg:pt-0">
        <Link
          href="/recommend"
          className="text-sm font-bold text-brand underline underline-offset-4"
        >
          로그인 없이 추천받기
        </Link>
      </p>
    </section>
  );
}

function loginErrorMessage(error: unknown): string {
  if (!(error instanceof ApiError)) {
    return "로그인하지 못했습니다. 잠시 후 다시 시도해 주세요.";
  }
  if (error.status === 401) return CREDENTIALS_ERROR;
  if (error.status === 429) return LOCKED_ERROR;
  // 422·500·연결 실패는 ApiError.message가 이미 사람이 읽을 한 문장이다.
  return error.message;
}

/** 로그인한 사람에게 로그인 폼을 또 보여주면 "로그인이 안 됐나?" 싶어진다. */
function AlreadySignedIn() {
  const { user } = useSession();
  return (
    <section className="mx-auto w-full max-w-[420px] lg:pt-10">
      <div className="lg:rounded-card lg:border lg:border-line lg:bg-surface lg:p-8">
        <h1 className="text-[28px] font-bold tracking-tight">이미 로그인했어요</h1>
        <p className="mt-2 text-sm text-ink-2">
          {user?.nickname ?? user?.email} 님으로 로그인한 상태입니다. 다른 계정을 쓰려면
          마이페이지에서 로그아웃하세요.
        </p>
        <div className="mt-6">
          <ButtonLink href="/me" variant="dark" size="lg" className="w-full">
            마이페이지로 가기
          </ButtonLink>
        </div>
      </div>
    </section>
  );
}

const CloseIcon = () => (
  <svg viewBox="0 0 24 24" className="size-6" aria-hidden>
    <path
      d="M6 6 18 18M18 6 6 18"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
    />
  </svg>
);
