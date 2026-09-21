"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { useSession } from "@/components/auth/SessionProvider";
import { ChevronLeftIcon } from "@/components/shell/icons";
import { Button, ButtonLink } from "@/components/ui/Button";
import { Field } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";
import { ApiError } from "@/lib/api/client";
import { signup } from "@/lib/api/endpoints";

/**
 * 회원가입 폼 (F-11).
 *
 * POST /api/auth/signup은 201과 함께 세션 쿠키까지 실어 준다 — 가입한 순간
 * 이미 로그인 상태다. 그래서 가입 뒤에 로그인을 다시 부르지 않고, 응답이 준
 * User를 그대로 세션에 넘긴다.
 */

/** 백엔드 제한값. 여기 상수와 힌트 문구가 어긋나면 사용자만 두 번 틀린다. */
const MIN_PASSWORD = 8;

/** 서버까지 갔다 오지 않아도 확실히 틀린 모양만 거른다. 이메일 검증은 결국 서버 몫이다. */
const EMAIL_SHAPE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

const OFFLINE_ERROR = "서버에 연결하지 못했습니다. 백엔드가 실행 중인지 확인해 주세요.";

type FieldErrors = { email?: string; password?: string; passwordConfirm?: string };

/** 409는 "이미 가입된 이메일"이라 다시 시도할 일이 아니라 로그인할 일이다. */
type FormError = { message: string; offerLogin?: boolean };

export function SignupForm() {
  const router = useRouter();
  const { status, signIn } = useSession();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [passwordConfirm, setPasswordConfirm] = useState("");
  const [nickname, setNickname] = useState("");
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState<FormError | null>(null);
  const [pending, setPending] = useState(false);

  const offline = status === "unreachable";

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending || offline) return;

    const errors = validate({ email, password, passwordConfirm });
    setFieldErrors(errors);
    if (Object.keys(errors).length > 0) {
      // 서버까지 갔다 오면 422가 오는데 그 문장이 영어다
      // ("String should have at least 8 characters"). 여기서 먼저 막는다.
      setFormError(null);
      return;
    }

    setPending(true);
    setFormError(null);
    try {
      const trimmedNickname = nickname.trim();
      const user = await signup({
        email: email.trim(),
        password,
        // 빈 문자열을 보내면 빈 닉네임이 저장된다. 선택 항목은 빠진 채로 보낸다.
        ...(trimmedNickname === "" ? {} : { nickname: trimmedNickname }),
      });
      signIn(user);
      // 이미 쿠키가 발급됐다. 로그인 화면을 한 번 더 거치게 하지 않는다.
      router.push("/me");
    } catch (error) {
      setFormError(signupErrorMessage(error));
      setPending(false);
    }
  }

  if (status === "authenticated") {
    return <AlreadySignedIn />;
  }

  /*
   * min-h: 모바일에선 "가입하기"가 화면 아래쪽에 붙는다 (디자인). 116px은 셸이 이미
   * 쓰는 여백 — AppShell의 pb-24(96px, 탭바 자리)와 PageContainer의 pt-5(20px).
   */
  return (
    <section className="mx-auto flex min-h-[calc(100dvh-116px)] w-full max-w-[420px] flex-col pb-6 lg:min-h-0 lg:pt-10">
      <div className="flex flex-1 flex-col lg:block lg:rounded-card lg:border lg:border-line lg:bg-surface lg:p-8">
        <div className="mb-5 flex items-center gap-1 lg:mb-6 lg:gap-0">
          {/* 모바일은 상단 내비가 없다. 되돌아갈 길을 화면 안에 둔다. */}
          <Link
            href="/login"
            aria-label="뒤로"
            className="-ml-2 inline-flex size-10 items-center justify-center rounded-pill text-ink transition-colors hover:bg-sunken lg:hidden"
          >
            <ChevronLeftIcon className="size-6" />
          </Link>
          <h1 className="text-xl font-bold tracking-tight lg:text-[28px]">회원가입</h1>
        </div>

        {offline ? (
          <div role="alert" className="mb-5">
            <Notice>{OFFLINE_ERROR}</Notice>
          </div>
        ) : null}

        {formError ? (
          <div role="alert" className="mb-5">
            <Notice>
              {formError.message}
              {formError.offerLogin ? (
                <>
                  {" "}
                  <Link href="/login" className="font-bold underline underline-offset-4">
                    로그인하러 가기
                  </Link>
                </>
              ) : null}
            </Notice>
          </div>
        ) : null}

        <form onSubmit={handleSubmit} noValidate className="flex flex-1 flex-col lg:block">
          <div className="space-y-5">
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
              autoComplete="new-password"
              hint={`${MIN_PASSWORD}자 이상`}
              value={password}
              error={fieldErrors.password}
              onChange={(event) => setPassword(event.target.value)}
            />
            <Field
              label="비밀번호 확인"
              type="password"
              autoComplete="new-password"
              value={passwordConfirm}
              error={fieldErrors.passwordConfirm}
              onChange={(event) => setPasswordConfirm(event.target.value)}
            />
            <Field
              label="닉네임 (선택)"
              type="text"
              autoComplete="nickname"
              value={nickname}
              onChange={(event) => setNickname(event.target.value)}
            />

            {/* 위치를 왜 묻는지·무엇을 저장하는지는 가입을 누르기 전에 밝혀야 한다. */}
            <p className="rounded-field bg-sunken px-3.5 py-3 text-sm leading-relaxed text-ink-2">
              이메일과 닉네임만 저장해요. 위치는 충전소를 찾을 때만 쓰고 저장하지 않아요.
            </p>
          </div>

          {/* 모바일에선 화면 아래에 붙는다 (디자인). 데스크톱 카드 안에선 바로 이어진다. */}
          <div className="mt-auto pt-8 lg:mt-6 lg:pt-0">
            <Button
              type="submit"
              variant="dark"
              size="lg"
              className="w-full"
              disabled={pending || offline}
            >
              {pending ? "가입 중…" : "가입하기"}
            </Button>
          </div>
        </form>

        {/* 모바일에는 뒤로 가기 화살표가 이 역할을 한다. 데스크톱에만 문장으로 둔다. */}
        <p className="mt-5 hidden text-center text-sm text-ink-2 lg:block">
          이미 계정이 있나요?{" "}
          <Link href="/login" className="font-bold text-brand underline underline-offset-4">
            로그인
          </Link>
        </p>
      </div>
    </section>
  );
}

function validate(values: {
  email: string;
  password: string;
  passwordConfirm: string;
}): FieldErrors {
  const errors: FieldErrors = {};

  if (values.email.trim() === "") {
    errors.email = "이메일을 입력해 주세요.";
  } else if (!EMAIL_SHAPE.test(values.email.trim())) {
    errors.email = "이메일 주소를 다시 확인해 주세요.";
  }

  if (values.password.length < MIN_PASSWORD) {
    errors.password = `비밀번호는 ${MIN_PASSWORD}자 이상이어야 해요.`;
  }

  // 확인 칸은 비밀번호가 짧을 때도 검사한다. 두 번 나눠 알려주면 두 번 고쳐야 한다.
  if (values.passwordConfirm !== values.password) {
    errors.passwordConfirm = "비밀번호가 서로 다릅니다.";
  }

  return errors;
}

function signupErrorMessage(error: unknown): FormError {
  if (!(error instanceof ApiError)) {
    return { message: "가입하지 못했습니다. 잠시 후 다시 시도해 주세요." };
  }
  if (error.status === 409) {
    return { message: "이미 가입된 이메일이에요.", offerLogin: true };
  }
  // 422·500·연결 실패는 ApiError.message가 이미 사람이 읽을 한 문장이다.
  return { message: error.message };
}

/** 로그인한 사람에게 가입 폼을 보여주면 계정을 또 만들어야 하나 싶어진다. */
function AlreadySignedIn() {
  const { user } = useSession();
  return (
    <section className="mx-auto w-full max-w-[420px] lg:pt-10">
      <div className="lg:rounded-card lg:border lg:border-line lg:bg-surface lg:p-8">
        <h1 className="text-[28px] font-bold tracking-tight">이미 로그인했어요</h1>
        <p className="mt-2 text-sm text-ink-2">
          {user?.nickname ?? user?.email} 님으로 로그인한 상태입니다. 다른 계정을 만들려면
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
