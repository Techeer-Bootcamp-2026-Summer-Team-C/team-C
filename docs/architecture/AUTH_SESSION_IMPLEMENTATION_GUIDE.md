# Dashboard 로그인 인증 구현 기준

## 1. 문서 목적

이 문서는 React Dashboard의 로그인 식별자와 JWT Access Token 수명 정책을 정의한다. Dashboard는 사용자가 지정한 login ID와 password로 로그인한다. Agent의 mTLS 등록, heartbeat, telemetry 인증은 변경하지 않는다.

## 2. 확정 범위

현재 구현 범위는 다음과 같다.

- 사용자가 지정하는 `login_id`와 password 기반 로그인
- 내부 관계와 감사 로그에서 자동 생성 `user_id` 유지
- Argon2id password hash와 HS256 JWT Access Token 유지
- Access Token, 사용자 정보, 만료시각은 탭 단위 `sessionStorage`에 저장
- 기본 Access Token 만료 12시간
- 환경변수로 5분~7일 범위의 만료 시간 조정
- 명시적 로그아웃 시 frontend memory, `sessionStorage`, React Query cache 제거
- 요청마다 PostgreSQL에서 사용자 역할과 `ACTIVE` 상태 재확인

현재 범위에 포함하지 않는 기능은 다음과 같다.

- 공개 회원가입
- 이메일 인증과 이메일 기반 password reset
- Refresh Token
- 서버 session 또는 Redis session store
- 브라우저 탭을 닫은 뒤 로그인 자동 복구
- 다중 기기 session 관리

이 기능들이 실제 요구사항이 되기 전에는 별도 session table을 추가하지 않는다.

## 3. 사용자 식별자

`users.user_id`와 `users.login_id`의 역할을 분리한다.

| 필드 | 역할 |
| --- | --- |
| `user_id` | PostgreSQL PK, FK, 감사 로그 actor 식별자 |
| `login_id` | 사용자가 로그인 화면에 입력하는 공개 식별자 |
| `name` | Dashboard 표시 이름 |
| `password_hash` | Argon2id password hash |

`login_id` 규칙은 다음과 같다.

- 앞뒤 공백 제거 후 소문자로 정규화
- 길이 3~64자
- 영문 소문자 또는 숫자로 시작
- 영문, 숫자, `.`, `_`, `@`, `+`, `-` 허용
- `LOWER(login_id)` 기준으로 대소문자 구분 없이 unique
- `@`는 기존 이메일 계정 migration 호환을 위한 허용 문자이며 이메일 형식을 요구하지 않음

기존 데이터는 `0002_user_login_id` migration에서 `email` 값을 정규화한 뒤 `VARCHAR(64) login_id`로 rename한다. 신규 사용자 table을 추가하지 않는다.

## 4. 로그인 API

```http
POST /api/v1/auth/login
Content-Type: application/json
```

```json
{
  "loginId": "security-admin",
  "password": "password"
}
```

성공 응답은 다음 형태다.

```json
{
  "data": {
    "accessToken": "jwt",
    "tokenType": "Bearer",
    "expiresIn": 43200,
    "user": {
      "userId": 1,
      "loginId": "security-admin",
      "name": "Security Admin",
      "role": "ADMIN",
      "status": "ACTIVE",
      "locale": "EN"
    }
  },
  "meta": {
    "requestId": "req_example"
  }
}
```

없는 login ID와 잘못된 password는 동일한 `401 INVALID_CREDENTIALS` 응답을 사용한다. password 요청은 1~1,024자로 제한한다. `DISABLED` 계정은 현재 API 계약에 따라 `403 ACCOUNT_DISABLED`를 반환한다. Nginx는 로그인 요청을 IP별 분당 10회와 burst 10으로 제한하고 초과 시 `429 RATE_LIMITED`를 반환한다.

## 5. Access Token 정책

Access Token은 HS256 JWT이며 다음 claim을 포함한다.

- `sub`: 내부 `user_id`
- `role`: `ADMIN`, `ANALYST`, `VIEWER`
- `iat`: 발급 시각
- `exp`: 만료 시각

기본 수명은 43,200초(12시간)다.

```text
EDR_ACCESS_TOKEN_TTL_SECONDS=43200
```

설정 가능한 범위는 300초(5분)부터 604,800초(7일)까지다. Frontend는 응답의 `expiresIn`을 서버 설정값으로 취급하며 별도 상수를 갖지 않는다.

Access Token, `locale`을 포함한 `UserDto`, 실제 만료시각은 단일 auth key로 현재 탭의 `sessionStorage`에 기록한다. 새로고침 시 만료시각과 저장 형식을 검증한 뒤 복구하고, 인증 token을 설정한 다음 `GET /api/v1/users/me`로 Backend 사용자와 locale을 재동기화한다. 만료·손상·`401`·명시적 로그아웃 시 저장값과 React Query cache를 제거한다. 브라우저 재시작까지 유지하는 장기 인증은 Refresh Token 또는 서버 session을 별도로 설계한다.

## 6. Backend 구현 기준

- `LoginRequest.login_id`를 trim/lowercase 정규화하고 형식을 검증한다.
- `UserRepository.by_login_id()`는 삭제되지 않은 사용자를 대소문자 구분 없이 조회한다.
- password 원문은 DB, log, 응답에 기록하지 않는다.
- `local` 외 환경에서는 32자 미만 또는 기본 placeholder JWT secret으로 시작하지 않는다.
- JWT 만료는 `Settings.access_token_ttl_seconds`를 사용한다.
- 보호 API는 JWT 검증 후 현재 사용자 role과 `ACTIVE` 상태를 PostgreSQL에서 다시 확인한다.
- 로그인 성공 시 `last_login_at`과 `updated_at`을 갱신한다.
- `tools.create_admin`은 `--login-id`, `--name`을 받고 password는 `getpass` 또는 안전한 stdin으로 읽는다. 개발 환경에서 기존 계정을 재지정할 때만 `--reset-existing`을 사용한다.

## 7. Frontend 구현 기준

- 필드 label은 `Login ID`를 사용한다.
- login ID input은 `type="text"`, `autocomplete="username"`, `autocapitalize="none"`을 사용한다.
- password input은 `type="password"`, `autocomplete="current-password"`, `maxlength="1024"`를 사용한다.
- 요청 body는 `{loginId, password}`다.
- 로그인 성공 시 기존 intended route로 이동한다.
- 로그아웃 시 Access Token, 사용자 state, React Query cache를 제거한다.
- `401`은 현재 로그인 state를 제거하고 로그인 화면으로 이동한다.

## 8. 계정 운영

최초 ADMIN은 다음 명령으로 생성한다.

```text
python -m tools.create_admin --login-id <LOGIN_ID> --name <DISPLAY_NAME>
```

기존 개발 계정의 비밀번호를 재지정할 때는 `--reset-existing`을 추가한다.

공개 회원가입 API는 만들지 않는다. 이메일을 사용하지 않으므로 password 분실 시 관리자가 CLI 또는 향후 관리자 전용 기능으로 reset한다.

## 9. 검증 항목

### Backend

- login ID trim/lowercase 정규화
- 허용 문자와 길이 검증
- 대소문자 구분 없는 중복 방지
- 올바른 login ID와 password 로그인
- 잘못된 자격 증명과 `DISABLED` 계정 거부
- JWT `exp - iat`이 설정값과 일치
- 만료·변조 JWT 거부
- `0001` 이후 `0002` migration 적용과 rollback

### Frontend

- Login ID 필드 validation
- `{loginId, password}` 요청
- 로그인 전 intended route 복귀
- 로그인 성공 후 token, 사용자, 만료시각을 `sessionStorage`에 저장하고 새로고침 후 복구
- 명시적 로그아웃 후 cache 제거

### 계약

- OpenAPI와 생성 TypeScript schema의 `loginId` 일치
- `LoginData.expiresIn`이 Backend 설정값과 일치
- API spec, ERD, frontend spec의 필드명 일치
