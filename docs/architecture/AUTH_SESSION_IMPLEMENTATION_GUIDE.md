# Dashboard 인증 세션 완성 가이드

## 1. 문서 목적

이 문서는 현재 Dashboard 로그인 구현을 새로고침과 Access Token 만료에도 사용할 수 있는 인증 세션으로 완성하기 위한 구현 가이드다.

대상은 React Dashboard 사용자 인증이다. Agent의 mTLS 등록·heartbeat·telemetry 인증은 변경하지 않는다.

FastAPI 공식 문서는 JWT 발급, 비밀번호 해시 검증, `Response.set_cookie()` 사용법을 기준으로 삼는다. Refresh Token의 저장·회전·폐기, 브라우저 저장소와 CSRF 정책은 OWASP Session Management 및 CSRF 지침을 적용한다.

## 2. 현재 구현 상태

현재 완료된 기능은 다음과 같다.

- `POST /api/v1/auth/login`
- 이메일 trim/lowercase 정규화
- Argon2id 비밀번호 해시 및 검증
- HS256 JWT Access Token 발급과 검증
- `sub`, `role`, `iat`, `exp` claim
- Access Token 유효기간 1시간
- Bearer Token 기반 Dashboard API 보호
- 요청마다 PostgreSQL에서 사용자 역할과 `ACTIVE` 상태 재확인
- React memory에 Access Token과 사용자 저장
- 명시적 로그아웃 시 memory와 React Query cache 제거

현재 부족한 기능은 다음과 같다.

- 새로고침 후 로그인 복구
- Refresh Token과 서버 세션
- Refresh Token 회전 및 재사용 차단
- 서버 로그아웃과 세션 폐기
- 만료된 Access Token 자동 갱신
- 동시 `401`에 대한 단일 Refresh 요청
- 로그인·갱신 Rate Limit과 감사 로그
- 계정 비밀번호 재설정 및 역할별 사용자 생성 CLI

현재 프론트는 새로고침 시 인증 state가 `null`로 초기화되고, API 하나가 `401`을 반환하면 즉시 로그아웃한다. 이 동작은 JWT 자체의 문제가 아니라 세션 수명주기가 구현되지 않은 상태다.

## 3. 목표 구조

```text
Browser
  ├─ Access Token
  │    ├─ JWT
  │    ├─ React memory에만 저장
  │    └─ Authorization: Bearer 헤더로 전송
  │
  └─ Refresh Token
       ├─ 예측 불가능한 opaque random token
       ├─ HttpOnly + Secure + SameSite cookie
       ├─ JavaScript에서 읽지 않음
       └─ PostgreSQL에는 SHA-256 hash만 저장

Vercel Frontend
  └─ /api 요청을 HTTPS EC2 Backend로 전달

FastAPI Backend
  ├─ Access JWT 발급·검증
  ├─ Refresh Token 회전·폐기
  └─ PostgreSQL refresh_sessions 관리
```

권장 수명은 다음과 같다.

| 항목 | 권장값 | 설명 |
| --- | ---: | --- |
| Access Token | 15분 | 탈취 시 피해 시간을 줄이고 Refresh로 사용성을 보완한다. |
| Refresh Session | 7일 | 부트캠프 배포와 데모 사용성을 고려한 절대 만료 시간이다. |
| Refresh 회전 | 매 Refresh | 사용한 Refresh Token은 즉시 폐기한다. |
| 로그인 Rate Limit | IP·계정 기준 | 정확한 수치는 부하 테스트 후 확정하고 `429`를 반환한다. |

Refresh에 성공해도 최초 로그인에서 정한 `expires_at`을 연장하지 않는다. 사용자는 최대 7일 후 다시 비밀번호를 입력한다.

## 4. 핵심 설계 결정

### 4.1 Access Token

Access Token은 현재와 같이 JWT를 사용한다. 다만 다음 claim을 추가한다.

| claim | 용도 |
| --- | --- |
| `sub` | 문자열 사용자 ID |
| `role` | `ADMIN`, `ANALYST`, `VIEWER` |
| `sid` | 로그인 세션 family ID |
| `jti` | 개별 Access Token ID |
| `iss` | 고정 issuer, 예: `edr-c-api` |
| `aud` | 고정 audience, 예: `edr-c-dashboard` |
| `iat` | 발급 시각 |
| `nbf` | 사용 시작 시각 |
| `exp` | 만료 시각 |

서버는 JWT header가 요청한 알고리즘을 신뢰하지 않고 설정에 고정된 알고리즘만 허용한다. `iss`, `aud`, `exp`, `nbf`, `sub`, `sid`, `jti`를 모두 검증한다.

Access Token은 `localStorage`나 `sessionStorage`에 저장하지 않는다. 브라우저 JavaScript가 읽을 수 있는 저장소에 인증 토큰을 두면 XSS 한 번으로 토큰 전체가 노출될 수 있다.

### 4.2 Refresh Token

Refresh Token은 JWT가 아닌 opaque random token으로 생성한다.

```python
from secrets import token_urlsafe

refresh_token = token_urlsafe(32)
```

32 random bytes를 사용하고 PostgreSQL에는 다음 값만 저장한다.

```python
from hashlib import sha256

token_hash = sha256(refresh_token.encode("utf-8")).hexdigest()
```

Refresh Token 원문은 응답 body, DB, 애플리케이션 로그, 감사 로그에 저장하지 않는다.

### 4.3 Refresh Cookie

운영 환경의 권장 cookie는 다음과 같다.

```python
response.set_cookie(
    key="__Host-edr_refresh",
    value=refresh_token,
    max_age=7 * 24 * 60 * 60,
    path="/",
    domain=None,
    secure=True,
    httponly=True,
    samesite="lax",
)
```

`__Host-` prefix는 `Secure`, `Path=/`, Domain 미설정을 요구한다. 로컬 HTTP 개발에서는 별도 이름인 `edr_refresh`와 `secure=False`를 사용하고, 운영 설정과 섞이지 않게 환경별로 분리한다.

쿠키를 삭제할 때는 생성할 때와 같은 `key`, `path`, `domain`을 사용한다.

### 4.4 즉시 로그아웃

JWT는 발급 후 자체적으로 유효하므로 서버 세션과 연결하지 않으면 로그아웃 후에도 만료 전까지 사용할 수 있다.

Access Token의 `sid`에 session family ID를 넣고, 현재 사용자 확인 쿼리에서 다음을 함께 검증한다.

- 사용자가 `ACTIVE`인가
- JWT의 역할과 현재 역할이 같은가
- 해당 `sid`에 만료되지 않고 폐기되지 않은 Refresh Session이 하나 이상 있는가

로그아웃 시 family 전체를 폐기하면 해당 `sid`를 가진 기존 Access Token도 즉시 사용할 수 없어진다.

## 5. PostgreSQL 변경

기존 `users` 테이블은 유지하고 신규 migration으로 `refresh_sessions`를 추가한다.

권장 파일은 다음과 같다.

```text
migrations/postgresql/0002_refresh_sessions.up.sql
migrations/postgresql/0002_refresh_sessions.down.sql
```

권장 schema 초안은 다음과 같다. 실제 migration 작성 시 프로젝트 naming과 migration 검증 규칙에 맞춘다.

```sql
CREATE TABLE refresh_sessions (
    refresh_session_id UUID PRIMARY KEY,
    family_id UUID NOT NULL,
    user_id BIGINT NOT NULL REFERENCES users(user_id),
    token_hash CHAR(64) NOT NULL UNIQUE,
    issued_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    last_used_at TIMESTAMPTZ NULL,
    revoked_at TIMESTAMPTZ NULL,
    replaced_by_session_id UUID NULL REFERENCES refresh_sessions(refresh_session_id),
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CHECK (expires_at > issued_at)
);

CREATE INDEX idx_refresh_sessions_user_active
    ON refresh_sessions (user_id, expires_at)
    WHERE revoked_at IS NULL;

CREATE INDEX idx_refresh_sessions_family
    ON refresh_sessions (family_id, issued_at DESC);
```

IP 주소와 User-Agent 저장은 필수가 아니다. 저장한다면 운영 목적과 보관 기간을 정하고 개인정보·로그 정책에 반영한다.

## 6. API 계약

최소 API 구성은 세 개다.

| Method | Path | 변경 | 인증 |
| --- | --- | --- | --- |
| `POST` | `/api/v1/auth/login` | 기존 API 확장 | Public |
| `POST` | `/api/v1/auth/refresh` | 신규 | Refresh Cookie |
| `POST` | `/api/v1/auth/logout` | 신규 | Refresh Cookie, Bearer는 선택 |

`/auth/refresh` 응답에 Access Token과 `UserDto`를 함께 반환하면 `/auth/me`는 만들지 않아도 된다.

### 6.1 Login

처리 순서는 다음과 같다.

1. email을 trim/lowercase로 정규화한다.
2. 사용자가 없어도 dummy Argon2 hash를 한 번 검증해 계정 존재 여부에 따른 응답 시간 차이를 줄인다.
3. 비밀번호와 `ACTIVE` 상태를 검증한다.
4. Refresh Token과 family ID를 생성한다.
5. Refresh Token hash를 DB에 저장한다.
6. `sid=family_id`인 Access Token을 발급한다.
7. Refresh Cookie를 설정한다.
8. `last_login_at`을 갱신하고 성공 감사 로그를 기록한다.

기존 `LoginData` 형식은 유지한다.

```json
{
  "data": {
    "accessToken": "jwt",
    "tokenType": "Bearer",
    "expiresIn": 900,
    "user": {
      "userId": 1,
      "email": "analyst@example.com",
      "name": "Analyst",
      "role": "ANALYST",
      "status": "ACTIVE"
    }
  },
  "meta": {"requestId": "req_..."}
}
```

응답에는 `Cache-Control: no-store`를 설정한다.

### 6.2 Refresh

Request body는 사용하지 않고 Refresh Cookie를 읽는다.

Transaction 내부 처리 순서는 다음과 같다.

1. Cookie가 없으면 `401 INVALID_REFRESH_TOKEN`을 반환한다.
2. Token hash로 session row를 `SELECT ... FOR UPDATE`한다.
3. session, family, 사용자 상태와 절대 만료를 검증한다.
4. 새 Refresh Token과 row를 같은 `family_id`로 생성한다.
5. 기존 row를 revoke하고 `replaced_by_session_id`를 기록한다.
6. 새 Access Token과 사용자 정보를 반환한다.
7. 새 Refresh Cookie로 교체한다.

이미 revoke되어 교체된 Refresh Token이 다시 제출되면 token reuse로 판단하고 같은 family의 모든 session을 폐기한다.

### 6.3 Logout

처리 순서는 다음과 같다.

1. Refresh Cookie가 있으면 해당 family를 전부 revoke한다.
2. Cookie가 없거나 이미 revoke된 경우에도 성공으로 처리한다.
3. 브라우저 cookie를 삭제한다.
4. 로그아웃 감사 로그를 기록한다.

Logout은 여러 번 호출해도 같은 결과가 되는 idempotent API로 만든다.

## 7. FastAPI 구현 기준

### 7.1 Cookie 설정

FastAPI path operation에 `Response` parameter를 선언하고 `response.set_cookie()`를 사용한다. 이 방식은 기존 `response_model` 검증을 유지하면서 cookie를 추가할 수 있다.

### 7.2 로그인 시간 차이 완화

현재 코드는 사용자가 없으면 비밀번호 hash 검증을 생략한다. FastAPI 공식 보안 예제처럼 미리 준비한 dummy Argon2 hash를 검증한 뒤 동일한 `INVALID_CREDENTIALS`를 반환한다.

다음 정보는 로그인 실패 응답과 로그에서 구분해서 노출하지 않는다.

- 등록되지 않은 이메일
- 비밀번호 불일치
- 삭제된 사용자

`DISABLED` 상태를 사용자에게 명시할지는 운영 정책이다. 현재 계약을 유지한다면 올바른 비밀번호를 검증한 뒤에만 `ACCOUNT_DISABLED`를 반환한다.

### 7.3 401 응답

Bearer 인증 실패 응답에는 `WWW-Authenticate: Bearer`를 포함한다. Refresh 실패는 프론트가 재로그인 여부를 판단할 수 있도록 안정적인 error code를 사용한다.

권장 error code는 다음과 같다.

- `INVALID_CREDENTIALS`
- `ACCOUNT_DISABLED`
- `INVALID_TOKEN`
- `INVALID_REFRESH_TOKEN`
- `REFRESH_TOKEN_REUSED`

### 7.4 CSRF와 CORS

Refresh Cookie는 브라우저가 자동 전송하므로 `/auth/refresh`와 `/auth/logout`에 CSRF 방어가 필요하다.

이 프로젝트의 권장안은 다음과 같다.

- Vercel에서 `/api`를 EC2 Backend로 rewrite해 브라우저 기준 same-origin으로 사용한다.
- 상태 변경 요청은 JSON만 허용한다.
- 프론트는 `X-CSRF-Protection: 1` 같은 custom header를 보낸다.
- Backend는 custom header와 배포 Origin allowlist를 검증한다.
- CORS가 필요하면 `allow_credentials=True`를 사용하고 Origin, method, header를 명시한다.
- credential 요청에 `allow_origins=["*"]`를 사용하지 않는다.
- `SameSite`만으로 CSRF 전체가 해결된다고 가정하지 않는다.

## 8. Frontend 변경

### 8.1 Auth state

현재 `token | null`, `user | null`만으로는 앱 시작 시 미확인 상태와 비로그인 상태를 구분할 수 없다.

다음 상태를 사용한다.

```ts
type AuthStatus = "loading" | "authenticated" | "anonymous";
```

앱 시작 흐름은 다음과 같다.

```text
AuthProvider mount
  └─ POST /auth/refresh
       ├─ 200: token/user 저장 → authenticated
       └─ 401: token/user 제거 → anonymous
```

`loading` 중에는 로그인 화면으로 redirect하지 않고 인증 확인 UI를 표시한다.

### 8.2 401 재시도

API client는 보호 API가 `401 INVALID_TOKEN`을 반환하면 다음 순서로 처리한다.

1. 진행 중인 Refresh promise가 있으면 공유한다.
2. 없으면 Refresh를 한 번 시작한다.
3. 성공하면 새 Access Token으로 원 요청을 한 번만 재시도한다.
4. Refresh도 실패하면 최종 로그아웃한다.

로그인·Refresh 요청 자체에 자동 Refresh를 적용하면 무한 루프가 생길 수 있으므로 제외한다.

### 8.3 명시적 로그아웃

로그아웃 버튼은 서버의 `/auth/logout`을 먼저 호출한다. 네트워크 오류가 나더라도 로컬 token, user, Query cache는 제거하고 로그인 화면으로 이동한다.

### 8.4 사용자 안내

- 세션이 만료된 경우: 다시 로그인해야 한다는 메시지를 표시한다.
- 네트워크 오류인 경우: 로그인 만료로 오인해 즉시 로그아웃하지 않는다.
- 계정 비활성화인 경우: 일반 만료와 다른 안내를 표시한다.
- 현재 Login 화면의 “새로고침하면 재로그인” 문구는 제거한다.

## 9. 계정 운영 도구

공개 회원가입과 사용자 관리 REST API는 초기 배포 범위에서 제외한다.

대신 기존 `tools.create_admin`을 다음 명령을 제공하는 관리자 CLI로 확장하거나 별도 도구를 만든다.

- 사용자 생성: email, name, role, password
- 비밀번호 재설정
- 역할 변경
- 계정 활성화·비활성화
- 사용자 session 전체 폐기

비밀번호와 토큰은 명령행 인자로 받지 않고 `getpass` 또는 안전한 stdin을 사용한다.

## 10. 배포 설정

### 10.1 운영 환경변수

다음 설정을 환경변수로 관리한다.

```text
EDR_JWT_SECRET
EDR_JWT_ISSUER=edr-c-api
EDR_JWT_AUDIENCE=edr-c-dashboard
EDR_ACCESS_TOKEN_TTL_SECONDS=900
EDR_REFRESH_TOKEN_TTL_SECONDS=604800
EDR_REFRESH_COOKIE_NAME=__Host-edr_refresh
EDR_REFRESH_COOKIE_SECURE=true
EDR_ALLOWED_ORIGINS=https://<vercel-production-domain>
```

운영 secret은 repository, Docker image, Compose 파일에 넣지 않고 AWS Systems Manager Parameter Store 또는 Secrets Manager에서 주입한다.

### 10.2 HTTPS

운영 API는 HTTPS만 제공한다. HTTP 요청은 HTTPS로 redirect하고 Refresh Cookie에는 항상 `Secure`를 설정한다.

### 10.3 Vercel과 EC2

우선안은 Vercel `/api` rewrite다. 브라우저는 Vercel origin으로만 요청하고 Vercel이 EC2 HTTPS API에 전달한다.

직접 cross-origin으로 호출하는 경우에는 다음이 모두 필요하다.

- 정확한 Vercel production origin allowlist
- `allow_credentials=True`
- 명시적 method/header allowlist
- 프론트 `credentials: "include"`
- Preview URL을 무제한 regex로 허용하지 않는 정책

## 11. 테스트 계획

### 11.1 Backend

- 올바른 로그인과 cookie 속성
- 없는 이메일과 잘못된 비밀번호의 동일 error contract
- dummy hash 검증 경로
- `DISABLED` 로그인 거부
- Access JWT의 필수 claim, issuer, audience, expiry 검증
- Refresh 성공과 token rotation
- 만료·폐기·위조 Refresh Token 거부
- 교체된 Refresh Token 재사용 시 family 전체 폐기
- Logout idempotency와 cookie 삭제
- Logout 후 기존 Access Token 거부
- 역할 변경과 계정 비활성화 즉시 반영
- 허용하지 않은 Origin과 CSRF header 누락 거부
- Rate Limit `429`

### 11.2 Frontend

- 앱 시작 Refresh 성공 시 현재 route 유지
- 앱 시작 Refresh 실패 시 login 이동
- Access Token을 storage에 기록하지 않음
- API `401` 후 Refresh와 원 요청 1회 재시도
- 동시 `401`에서 Refresh 한 번만 호출
- Refresh 실패 시 한 번만 logout
- 네트워크 오류는 자동 logout하지 않음
- 명시적 logout 후 cache 제거
- 무한 Refresh loop가 없음

### 11.3 Browser E2E

```text
로그인
→ 보호 화면 이동
→ 브라우저 새로고침
→ 같은 화면과 사용자 유지
→ Access Token 만료 유도
→ 자동 갱신 확인
→ 로그아웃
→ 새로고침
→ 로그인 화면 확인
```

개발자 도구에서 다음도 확인한다.

- Access Token이 Local Storage와 Session Storage에 없음
- Refresh Cookie가 JavaScript에서 보이지 않음
- 운영 Cookie에 Secure, HttpOnly, SameSite가 있음
- Refresh Token이 response body와 log에 없음

## 12. 변경 대상 파일

구현 시 최소 변경 대상은 다음과 같다.

```text
backend/auth.py
backend/main.py
backend/settings.py
backend/contracts/auth.py
backend/contracts/api_manifest.py
backend/storage/postgres.py
migrations/postgresql/0002_refresh_sessions.up.sql
migrations/postgresql/0002_refresh_sessions.down.sql
frontend/src/api/client.ts
frontend/src/api/endpoints.ts
frontend/src/auth/AuthContext.tsx
frontend/src/pages/LoginPage.tsx
frontend/tests/api-client.test.ts
frontend/tests/auth-routing.test.tsx
tests/test_backend_support_contracts.py
tests/test_dashboard_api_integration.py
.env.example
docs/contracts/API_SPEC.md
docs/frontend/FRONTEND_SPEC.md
openapi/openapi.json
frontend/src/api/generated/schema.ts
```

기존 ERD 문서도 `refresh_sessions`가 최종 설계에 포함되는 시점에 함께 갱신한다.

## 13. 권장 구현 순서

1. API 계약과 error code 확정
2. PostgreSQL migration 작성
3. Refresh Session repository와 token helper 구현
4. Login 확장, Refresh, Logout API 구현
5. Backend 단위·통합 테스트
6. Frontend Auth state와 single-flight Refresh 구현
7. Frontend 테스트와 브라우저 E2E
8. Vercel rewrite, EC2 HTTPS, Cookie 검증
9. API_SPEC, FRONTEND_SPEC, OpenAPI, ERD 동기화

## 14. 완료 조건

다음 조건을 모두 만족해야 로그인 기능을 완료로 본다.

- 새로고침 후 로그인과 현재 route가 유지된다.
- Access Token은 브라우저 storage에 남지 않는다.
- Refresh Token은 HttpOnly cookie와 DB hash로만 존재한다.
- Refresh Token은 사용할 때마다 회전한다.
- Logout과 계정 비활성화가 기존 세션을 서버에서 무효화한다.
- 네트워크 오류와 인증 만료가 사용자에게 구분된다.
- 동시 `401`과 Refresh 실패가 무한 요청을 만들지 않는다.
- 운영 환경에서 HTTPS와 Cookie 속성을 브라우저로 검증한다.
- 인증 관련 Backend, Frontend, E2E 테스트가 통과한다.
- API, OpenAPI, Frontend, ERD 문서가 같은 계약을 설명한다.

## 15. 공식 참고 자료

- [FastAPI - OAuth2 with Password, Bearer and JWT](https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/)
- [FastAPI - Response Cookies](https://fastapi.tiangolo.com/advanced/response-cookies/)
- [FastAPI - CORS](https://fastapi.tiangolo.com/tutorial/cors/)
- [Starlette - Response set_cookie/delete_cookie](https://www.starlette.io/responses/)
- [Python - secrets](https://docs.python.org/3/library/secrets.html)
- [PyJWT - Usage Examples](https://pyjwt.readthedocs.io/en/stable/usage.html)
- [OWASP - Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
- [OWASP - Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)
- [OWASP - REST Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html)
