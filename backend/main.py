import logging
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID, uuid4

import psycopg
import pyarrow
from botocore.exceptions import BotoCoreError
from clickhouse_connect.driver.exceptions import ClickHouseError
from confluent_kafka import KafkaException
from fastapi import Depends, FastAPI, Path, Query, Request, Response
from fastapi.exceptions import RequestValidationError as FastApiRequestValidationError
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .agent_identity import trusted_agent_identity
from .api_services import AlertService, EndpointService, IncidentService
from .archive_service import ArchiveService, archive_bucket
from .auth import AuthenticatedUser, decode_access_token, issue_access_token, require_write_role, verify_password
from .collector import CollectorService
from .contracts.alerts import AlertDetailDto, AlertDto, AlertStatusUpdateRequest
from .contracts.archives import ArchiveBucketDto, ArchiveRestoreRequest, ArchiveRestoreStartDto
from .contracts.auth import LoginData, LoginRequest, UserDto, UserLocaleUpdateRequest
from .contracts.collector import (
    AgentHeartbeatData,
    AgentHeartbeatRequest,
    AgentRegisterData,
    AgentRegisterRequest,
    TelemetryBatchData,
    TelemetryBatchRequest,
)
from .contracts.common import ErrorBody, ErrorDetail, ErrorEnvelope, PagedData, RequestMeta, SuccessEnvelope
from .contracts.dashboard import DashboardSummaryDto, EndpointSummaryDto, IngestSummaryDto
from .contracts.dashboard_layouts import DashboardLayoutDto, DashboardLayoutPutRequest
from .contracts.endpoints import EndpointDetailDto, EndpointDto
from .contracts.enums import DashboardInterval, UserLocale, UserRole, UserStatus
from .contracts.events import EventDetailDto, EventDto, ProcessTreeDto
from .contracts.incidents import IncidentDetailDto, IncidentDto
from .contracts.intelligence import (
    CorrelationDto,
    DnsLookupDto,
    DnsLookupQuery,
    ForwardDnsDto,
    ForwardDnsQuery,
    ReverseDnsDto,
    ReverseDnsQuery,
)
from .contracts.investigations import AttackTimelineDto, EgressTopologyDto, EventFailureDto, IncidentInvestigationDto
from .contracts.operations import OperationsHealthDto
from .contracts.requests import (
    AlertListQuery,
    ArchiveRestoreListQuery,
    CorrelationQuery,
    DashboardSummaryQuery,
    DashboardTimeQuery,
    EndpointListQuery,
    EventDetailQuery,
    EventListQuery,
    FailureListQuery,
    IncidentListQuery,
    ProcessTreeQuery,
    TopologyQuery,
)
from .dashboard_layouts import DashboardLayoutService
from .dns_service import DnsIntelligenceService
from .errors import ApplicationError, RequestValidationError, ServiceUnavailableError
from .event_service import EventService
from .investigation_service import FailureService, InvestigationService
from .operations_service import OperationsHealthService
from .runtime import RuntimeServices
from .settings import get_settings
from .storage.clickhouse import EventRepository, FailureRepository
from .storage.models import AgentCertificateIdentity
from .storage.postgres import (
    AlertRepository,
    DashboardLayoutRepository,
    EndpointRepository,
    IncidentRepository,
    IngestMetadataRepository,
    UserRepository,
)
from .summary_service import SummaryService
from .time_range import resolve_time_range

OPENAPI_TAGS = [
    {"name": "Auth", "description": "대시보드 사용자 인증과 JWT 액세스 토큰 발급 기능입니다."},
    {"name": "Users", "description": "인증된 대시보드 사용자의 프로필과 환경설정을 관리합니다."},
    {"name": "Endpoints", "description": "엔드포인트 목록, 상태, 백엔드 산정 위험도와 프로세스 트리를 조회합니다."},
    {"name": "Events", "description": "ClickHouse HOT 데이터와 복원된 Parquet 이벤트 증거를 조회합니다."},
    {"name": "Archives", "description": "아카이브 버킷의 복원 요청과 진행 상태를 관리합니다."},
    {"name": "Alerts", "description": "RuleV1 탐지 결과와 Alert 처리 상태를 조회하고 변경합니다."},
    {"name": "Incidents", "description": "상관분석으로 생성된 Incident와 조사 정보를 읽기 전용으로 제공합니다."},
    {"name": "Dashboard", "description": "백엔드가 계산한 보안, 수집, 토폴로지 요약과 대시보드 레이아웃을 제공합니다."},
    {"name": "Operations", "description": "의존 서비스, 파이프라인 워커와 실패 이벤트의 운영 상태를 제공합니다."},
    {"name": "Intelligence", "description": "DNS 조회와 IP·Domain·이벤트 간 상관분석 기능을 제공합니다."},
    {"name": "Collector", "description": "mTLS로 인증된 Agent 등록, heartbeat, 텔레메트리 수집 기능입니다."},
]

ERROR_DESCRIPTIONS = {
    400: "요청 형식 또는 입력값 검증에 실패했습니다.",
    401: "인증에 실패했거나 유효한 인증 정보가 없습니다.",
    403: "인증된 주체에게 이 작업을 수행할 권한이 없습니다.",
    404: "요청한 리소스를 찾을 수 없습니다.",
    409: "현재 리소스, 인증 주체 또는 Archive 상태와 요청이 충돌합니다.",
    413: "요청 본문 크기 또는 이벤트 수가 허용 한도를 초과했습니다.",
    429: "설정된 요청 속도 제한을 초과했습니다.",
    503: "필수 의존 서비스를 일시적으로 사용할 수 없습니다.",
}

BEARER = HTTPBearer(
    auto_error=False,
    scheme_name="BearerJWT",
    description="POST /api/v1/auth/login에서 발급받은 JWT 액세스 토큰을 입력합니다.",
)
LOGGER = logging.getLogger(__name__)
INFRASTRUCTURE_EXCEPTIONS = (psycopg.Error, ClickHouseError, BotoCoreError, KafkaException, pyarrow.ArrowException)


def _error_responses(*statuses: int) -> dict[int, dict[str, object]]:
    return {status: {"model": ErrorEnvelope, "description": ERROR_DESCRIPTIONS[status]} for status in statuses}


def get_collector_service(request: Request) -> CollectorService:
    return CollectorService(_runtime(request))


def current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(BEARER)],
) -> AuthenticatedUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise ApplicationError(401, "INVALID_TOKEN", "A valid Bearer token is required.")
    runtime = _runtime(request)
    user = decode_access_token(credentials.credentials, secret=runtime.settings.jwt_secret.get_secret_value())
    with runtime.postgres() as connection:
        identity = UserRepository(connection).active_identity(user.user_id)
    if identity is None or identity[1] is not UserStatus.ACTIVE or identity[0] is not user.role:
        raise ApplicationError(401, "INVALID_TOKEN", "The access token identity is no longer active.")
    return user


def create_app(runtime: RuntimeServices | None = None) -> FastAPI:
    app = FastAPI(
        title="EDR_C API",
        description=(
            "EDR_C 대시보드와 수집 Agent가 사용하는 API입니다. "
            "대시보드 API는 Bearer JWT, Collector API는 mTLS 클라이언트 인증서를 사용합니다."
        ),
        version="0.1.0",
        docs_url="/docs",
        openapi_url="/openapi.json",
        openapi_tags=OPENAPI_TAGS,
    )
    app.state.runtime = runtime

    def custom_openapi() -> dict[str, object]:
        return _openapi_schema(app)

    app.openapi = custom_openapi

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        request.state.request_id = request.headers.get("X-Request-ID") or f"req_{uuid4()}"
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    @app.exception_handler(ApplicationError)
    async def application_error_handler(request: Request, error: ApplicationError) -> JSONResponse:
        return JSONResponse(
            status_code=error.status_code,
            content=_error_envelope(request, error).model_dump(mode="json", by_alias=True),
        )

    @app.exception_handler(FastApiRequestValidationError)
    async def validation_error_handler(request: Request, _error: FastApiRequestValidationError) -> JSONResponse:
        error = RequestValidationError("Request validation failed.")
        return JSONResponse(
            status_code=400,
            content=_error_envelope(request, error).model_dump(mode="json", by_alias=True),
        )

    async def infrastructure_error_handler(request: Request, error: Exception) -> JSONResponse:
        LOGGER.error(
            "Required infrastructure dependency failed request_id=%s",
            request.state.request_id,
            exc_info=(type(error), error, error.__traceback__),
        )
        unavailable = ServiceUnavailableError("A required dependency is temporarily unavailable.")
        return JSONResponse(
            status_code=unavailable.status_code,
            content=_error_envelope(request, unavailable).model_dump(mode="json", by_alias=True),
        )

    for exception_type in INFRASTRUCTURE_EXCEPTIONS:
        app.add_exception_handler(exception_type, infrastructure_error_handler)

    @app.get("/health/live", include_in_schema=False)
    def live() -> dict[str, str]:
        return {"status": "live"}

    @app.get("/health/ready", include_in_schema=False)
    def ready(request: Request) -> dict[str, str]:
        try:
            _runtime(request).check_ready()
        except Exception as error:
            raise ServiceUnavailableError("A required dependency is not ready.") from error
        return {"status": "ready"}

    @app.post(
        "/api/v1/auth/login",
        response_model=SuccessEnvelope[LoginData],
        operation_id="authLogin",
        summary="대시보드 로그인",
        description="로그인 ID와 비밀번호를 검증하고 대시보드 API 호출에 사용할 Bearer JWT를 발급합니다.",
        tags=["Auth"],
        responses=_error_responses(400, 401, 403, 429, 503),
    )
    def login(request: Request, body: LoginRequest) -> SuccessEnvelope[LoginData]:
        runtime = _runtime(request)
        with runtime.postgres() as connection:
            row = UserRepository(connection).by_login_id(body.login_id)
            if row is None or not verify_password(str(row["password_hash"]), body.password):
                raise ApplicationError(401, "INVALID_CREDENTIALS", "Login ID or password is incorrect.")
            if row["status"] == UserStatus.DISABLED.value:
                raise ApplicationError(403, "ACCOUNT_DISABLED", "The account is disabled.")
            now = datetime.now(UTC)
            role = UserRole(row["role"])
            token = issue_access_token(
                user_id=int(row["user_id"]),
                role=role,
                secret=runtime.settings.jwt_secret.get_secret_value(),
                now=now,
                expires_in_seconds=runtime.settings.access_token_ttl_seconds,
            )
            connection.execute(
                "UPDATE users SET last_login_at = %s, updated_at = %s WHERE user_id = %s", (now, now, row["user_id"])
            )
            connection.commit()
        data = LoginData(
            access_token=token,
            token_type="Bearer",
            expires_in=runtime.settings.access_token_ttl_seconds,
            user=UserDto(
                user_id=row["user_id"],
                login_id=row["login_id"],
                name=row["name"],
                role=role,
                status=UserStatus.ACTIVE,
                locale=UserLocale(row["locale"]),
            ),
        )
        return _success(request, data)

    @app.get(
        "/api/v1/users/me",
        response_model=SuccessEnvelope[UserDto],
        operation_id="usersMeGet",
        summary="내 사용자 정보 조회",
        description="현재 Bearer JWT에 연결된 활성 사용자의 프로필, 권한, 언어 설정을 조회합니다.",
        tags=["Users"],
        responses=_error_responses(401, 503),
    )
    def users_me(
        request: Request,
        user: Annotated[AuthenticatedUser, Depends(current_user)],
    ) -> SuccessEnvelope[UserDto]:
        runtime = _runtime(request)
        with runtime.postgres() as connection:
            row = UserRepository(connection).by_user_id(user.user_id)
        if row is None:
            raise ApplicationError(401, "INVALID_TOKEN", "The access token identity is no longer active.")
        return _success(request, _user_dto(row))

    @app.patch(
        "/api/v1/users/me/locale",
        response_model=SuccessEnvelope[UserDto],
        operation_id="usersLocaleUpdate",
        summary="내 언어 설정 변경",
        description="현재 사용자의 대시보드 표시 언어를 변경하고 갱신된 사용자 정보를 반환합니다.",
        tags=["Users"],
        responses=_error_responses(400, 401, 503),
    )
    def update_user_locale(
        request: Request,
        body: UserLocaleUpdateRequest,
        user: Annotated[AuthenticatedUser, Depends(current_user)],
    ) -> SuccessEnvelope[UserDto]:
        runtime = _runtime(request)
        with runtime.postgres() as connection:
            row = UserRepository(connection).update_locale(
                user_id=user.user_id,
                locale=body.locale,
                request_id=request.state.request_id,
                changed_at=datetime.now(UTC),
            )
        if row is None:
            raise ApplicationError(401, "INVALID_TOKEN", "The access token identity is no longer active.")
        return _success(request, _user_dto(row))

    @app.get(
        "/api/v1/endpoints",
        response_model=SuccessEnvelope[PagedData[EndpointDto]],
        operation_id="endpointsList",
        summary="엔드포인트 목록 조회",
        description="검색, 상태, 운영체제, 위험도 조건을 적용해 엔드포인트 목록을 페이지 단위로 조회합니다.",
        tags=["Endpoints"],
        responses=_error_responses(400, 401, 503),
    )
    def endpoints(
        request: Request,
        query: Annotated[EndpointListQuery, Query()],
        _user: Annotated[AuthenticatedUser, Depends(current_user)],
    ) -> SuccessEnvelope[PagedData[EndpointDto]]:
        calculated_at = datetime.now(UTC)
        runtime = _runtime(request)
        with runtime.postgres() as connection:
            data = EndpointService(EndpointRepository(connection)).list(query, calculated_at=calculated_at)
        return _success(request, data)

    @app.get(
        "/api/v1/endpoints/{endpointId}",
        response_model=SuccessEnvelope[EndpointDetailDto],
        operation_id="endpointsGet",
        summary="엔드포인트 상세 조회",
        description="엔드포인트 기본 정보, 센서 상태, 최근 활동과 백엔드 산정 위험도를 조회합니다.",
        tags=["Endpoints"],
        responses=_error_responses(400, 401, 404, 503),
    )
    def endpoint_detail(
        endpointId: Annotated[int, Path(description="조회할 엔드포인트 ID입니다.")],
        request: Request,
        _user: Annotated[AuthenticatedUser, Depends(current_user)],
    ) -> SuccessEnvelope[EndpointDetailDto]:
        runtime = _runtime(request)
        with runtime.postgres() as connection:
            data = EndpointService(EndpointRepository(connection)).detail(endpointId, calculated_at=datetime.now(UTC))
        return _success(request, data)

    @app.get(
        "/api/v1/endpoints/{endpointId}/process-tree",
        response_model=SuccessEnvelope[ProcessTreeDto],
        operation_id="endpointsGetProcessTree",
        summary="엔드포인트 프로세스 트리 조회",
        description="지정한 시간 범위에서 수집된 프로세스 실행 이벤트를 부모·자식 트리로 구성해 반환합니다.",
        tags=["Endpoints"],
        responses=_error_responses(400, 401, 503),
    )
    def endpoint_process_tree(
        endpointId: Annotated[int, Path(description="프로세스 트리를 조회할 엔드포인트 ID입니다.")],
        request: Request,
        query: Annotated[ProcessTreeQuery, Query()],
        _user: Annotated[AuthenticatedUser, Depends(current_user)],
    ) -> SuccessEnvelope[ProcessTreeDto]:
        runtime = _runtime(request)
        from_, to = resolve_time_range(query, now=datetime.now(UTC))
        with runtime.postgres() as connection:
            data = _investigation_service(runtime, connection).process_tree(
                endpointId,
                from_=from_,
                to=to,
                selected_pid=query.selected_pid,
            )
        return _success(request, data)

    @app.get(
        "/api/v1/events",
        response_model=SuccessEnvelope[PagedData[EventDto]],
        operation_id="eventsList",
        summary="이벤트 목록 조회",
        description="HOT 또는 복원된 저장소에서 시간, 엔드포인트, 이벤트 유형 조건으로 이벤트 증거를 조회합니다.",
        tags=["Events"],
        responses=_error_responses(400, 401, 409, 503),
    )
    def events(
        request: Request,
        query: Annotated[EventListQuery, Query()],
        _user: Annotated[AuthenticatedUser, Depends(current_user)],
    ) -> SuccessEnvelope[PagedData[EventDto]]:
        runtime = _runtime(request)
        from_, to = resolve_time_range(query, now=datetime.now(UTC))
        with runtime.postgres() as connection:
            items, total = _event_service(runtime, connection).list_rows(query, from_=from_, to=to)
        return _success(request, PagedData(items=items, page=query.page, size=query.size, total=total))

    @app.get(
        "/api/v1/events/{eventId}",
        response_model=SuccessEnvelope[EventDetailDto],
        operation_id="eventsGet",
        summary="이벤트 상세 조회",
        description="이벤트 ID와 저장 위치 식별 조건을 사용해 단일 이벤트의 상세 증거를 조회합니다.",
        tags=["Events"],
        responses=_error_responses(400, 401, 404, 409, 503),
    )
    def event_detail(
        eventId: Annotated[UUID, Path(description="조회할 이벤트 UUID입니다.")],
        request: Request,
        query: Annotated[EventDetailQuery, Query()],
        _user: Annotated[AuthenticatedUser, Depends(current_user)],
    ) -> SuccessEnvelope[EventDetailDto]:
        runtime = _runtime(request)
        with runtime.postgres() as connection:
            data = _event_service(runtime, connection).detail(
                event_id=eventId, endpoint_id=query.endpoint_id, occurred_at=query.occurred_at
            )
        if data is None:
            raise ApplicationError(404, "NOT_FOUND", "Event was not found.")
        return _success(request, data)

    @app.get(
        "/api/v1/failures",
        response_model=SuccessEnvelope[PagedData[EventFailureDto]],
        operation_id="failuresList",
        summary="파이프라인 실패 목록 조회",
        description="수집, 검증, 저장 단계에서 발생한 실패 이벤트와 재처리 상태를 페이지 단위로 조회합니다.",
        tags=["Operations"],
        responses=_error_responses(400, 401, 503),
    )
    def failures(
        request: Request,
        query: Annotated[FailureListQuery, Query()],
        _user: Annotated[AuthenticatedUser, Depends(current_user)],
    ) -> SuccessEnvelope[PagedData[EventFailureDto]]:
        runtime = _runtime(request)
        from_, to = resolve_time_range(query, now=datetime.now(UTC))
        data = FailureService(FailureRepository(runtime.clickhouse)).list(query, from_=from_, to=to)
        return _success(request, data)

    @app.post(
        "/api/v1/archives/restores",
        response_model=SuccessEnvelope[ArchiveRestoreStartDto],
        operation_id="archiveRestoresStart",
        summary="아카이브 복원 시작",
        description="선택한 엔드포인트와 시간 범위의 아카이브 데이터를 조회 가능한 RESTORED 영역으로 복원 요청합니다.",
        tags=["Archives"],
        responses={
            202: {"model": SuccessEnvelope[ArchiveRestoreStartDto], "description": "복원 요청을 접수했습니다."},
            **_error_responses(400, 401, 403, 503),
        },
    )
    def restore_start(
        request: Request,
        body: ArchiveRestoreRequest,
        response: Response,
        user: Annotated[AuthenticatedUser, Depends(current_user)],
    ) -> SuccessEnvelope[ArchiveRestoreStartDto]:
        require_write_role(user)
        runtime = _runtime(request)
        with runtime.postgres() as connection:
            data, status_code = ArchiveService(
                IngestMetadataRepository(connection), runtime.restore_client
            ).start_restore(
                body,
                actor_identifier=str(user.user_id),
                request_id=request.state.request_id,
                now=datetime.now(UTC),
            )
        response.status_code = status_code
        return _success(request, data)

    @app.get(
        "/api/v1/archives/restores",
        response_model=SuccessEnvelope[PagedData[ArchiveBucketDto]],
        operation_id="archiveRestoresList",
        summary="아카이브 복원 목록 조회",
        description="엔드포인트와 시간 범위에 해당하는 아카이브 버킷의 복원 상태를 페이지 단위로 조회합니다.",
        tags=["Archives"],
        responses=_error_responses(400, 401, 503),
    )
    def restore_list(
        request: Request,
        query: Annotated[ArchiveRestoreListQuery, Query()],
        _user: Annotated[AuthenticatedUser, Depends(current_user)],
    ) -> SuccessEnvelope[PagedData[ArchiveBucketDto]]:
        runtime = _runtime(request)
        with runtime.postgres() as connection:
            repository = IngestMetadataRepository(connection)
            rows = repository.restore_buckets(
                query.endpoint_ids,
                query.from_,
                query.to,
                limit=query.size,
                offset=(query.page - 1) * query.size,
            )
            total = repository.count_restore_buckets(query.endpoint_ids, query.from_, query.to)
        data = PagedData(
            items=[archive_bucket(row) for row in rows],
            page=query.page,
            size=query.size,
            total=total,
        )
        return _success(request, data)

    @app.get(
        "/api/v1/alerts",
        response_model=SuccessEnvelope[PagedData[AlertDto]],
        operation_id="alertsList",
        summary="Alert 목록 조회",
        description="탐지 시각, 심각도, 상태, 엔드포인트 조건으로 Alert 목록을 페이지 단위로 조회합니다.",
        tags=["Alerts"],
        responses=_error_responses(400, 401, 503),
    )
    def alerts(
        request: Request,
        query: Annotated[AlertListQuery, Query()],
        _user: Annotated[AuthenticatedUser, Depends(current_user)],
    ) -> SuccessEnvelope[PagedData[AlertDto]]:
        runtime = _runtime(request)
        from_, to = resolve_time_range(query, now=datetime.now(UTC))
        with runtime.postgres() as connection:
            data = _alert_service(runtime, connection).list(query, from_=from_, to=to)
        return _success(request, data)

    @app.get(
        "/api/v1/alerts/{alertId}",
        response_model=SuccessEnvelope[AlertDetailDto],
        operation_id="alertsGet",
        summary="Alert 상세 조회",
        description="Alert의 탐지 규칙, 관련 이벤트, MITRE ATT&CK 정보와 대응 지침을 조회합니다.",
        tags=["Alerts"],
        responses=_error_responses(400, 401, 404, 503),
    )
    def alert_detail(
        alertId: Annotated[int, Path(description="조회할 Alert ID입니다.")],
        request: Request,
        _user: Annotated[AuthenticatedUser, Depends(current_user)],
    ) -> SuccessEnvelope[AlertDetailDto]:
        runtime = _runtime(request)
        with runtime.postgres() as connection:
            data = _alert_service(runtime, connection).detail(alertId)
        return _success(request, data)

    @app.patch(
        "/api/v1/alerts/{alertId}/status",
        response_model=SuccessEnvelope[AlertDto],
        operation_id="alertsUpdateStatus",
        summary="Alert 상태 변경",
        description="쓰기 권한이 있는 사용자가 Alert 처리 상태를 변경합니다. 변경 내용은 감사 정보와 함께 기록됩니다.",
        tags=["Alerts"],
        responses=_error_responses(400, 401, 403, 404, 503),
    )
    def alert_status(
        alertId: Annotated[int, Path(description="상태를 변경할 Alert ID입니다.")],
        request: Request,
        body: AlertStatusUpdateRequest,
        user: Annotated[AuthenticatedUser, Depends(current_user)],
    ) -> SuccessEnvelope[AlertDto]:
        require_write_role(user)
        runtime = _runtime(request)
        with runtime.postgres() as connection:
            data = _alert_service(runtime, connection).update_status(
                alertId,
                status=body.status,
                actor_identifier=str(user.user_id),
                request_id=request.state.request_id,
                changed_at=datetime.now(UTC),
            )
        return _success(request, data)

    @app.get(
        "/api/v1/incidents",
        response_model=SuccessEnvelope[PagedData[IncidentDto]],
        operation_id="incidentsList",
        summary="Incident 목록 조회",
        description="상관분석으로 생성된 Incident를 시간, 심각도, 상태 조건으로 페이지 단위 조회합니다.",
        tags=["Incidents"],
        responses=_error_responses(400, 401, 503),
    )
    def incidents(
        request: Request,
        query: Annotated[IncidentListQuery, Query()],
        _user: Annotated[AuthenticatedUser, Depends(current_user)],
    ) -> SuccessEnvelope[PagedData[IncidentDto]]:
        runtime = _runtime(request)
        from_, to = resolve_time_range(query, now=datetime.now(UTC))
        with runtime.postgres() as connection:
            data = IncidentService(IncidentRepository(connection)).list(query, from_=from_, to=to)
        return _success(request, data)

    @app.get(
        "/api/v1/incidents/{incidentId}",
        response_model=SuccessEnvelope[IncidentDetailDto],
        operation_id="incidentsGet",
        summary="Incident 상세 조회",
        description="Incident 기본 정보, 위험도, 관련 엔드포인트와 연결된 Alert를 조회합니다.",
        tags=["Incidents"],
        responses=_error_responses(400, 401, 404, 503),
    )
    def incident_detail(
        incidentId: Annotated[int, Path(description="조회할 Incident ID입니다.")],
        request: Request,
        _user: Annotated[AuthenticatedUser, Depends(current_user)],
    ) -> SuccessEnvelope[IncidentDetailDto]:
        runtime = _runtime(request)
        with runtime.postgres() as connection:
            data = IncidentService(IncidentRepository(connection)).detail(incidentId)
        return _success(request, data)

    @app.get(
        "/api/v1/incidents/{incidentId}/timeline",
        response_model=SuccessEnvelope[AttackTimelineDto],
        operation_id="incidentsGetTimeline",
        summary="Incident 공격 타임라인 조회",
        description="Incident에 연결된 이벤트와 Alert를 시간순 공격 타임라인으로 구성해 반환합니다.",
        tags=["Incidents"],
        responses=_error_responses(400, 401, 404, 503),
    )
    def incident_timeline(
        incidentId: Annotated[int, Path(description="타임라인을 조회할 Incident ID입니다.")],
        request: Request,
        _user: Annotated[AuthenticatedUser, Depends(current_user)],
    ) -> SuccessEnvelope[AttackTimelineDto]:
        runtime = _runtime(request)
        with runtime.postgres() as connection:
            data = _investigation_service(runtime, connection).timeline(incidentId)
        return _success(request, data)

    @app.get(
        "/api/v1/incidents/{incidentId}/investigation",
        response_model=SuccessEnvelope[IncidentInvestigationDto],
        operation_id="incidentsGetInvestigation",
        summary="Incident 조사 그래프 조회",
        description="Incident의 이벤트, Alert, 엔드포인트와 관찰값을 조사 그래프의 노드와 관계로 반환합니다.",
        tags=["Incidents"],
        responses=_error_responses(400, 401, 404, 503),
    )
    def incident_investigation(
        incidentId: Annotated[int, Path(description="조사 그래프를 조회할 Incident ID입니다.")],
        request: Request,
        _user: Annotated[AuthenticatedUser, Depends(current_user)],
    ) -> SuccessEnvelope[IncidentInvestigationDto]:
        runtime = _runtime(request)
        with runtime.postgres() as connection:
            data = _investigation_service(runtime, connection).investigation(incidentId)
        return _success(request, data)

    @app.get(
        "/api/v1/dashboard/summary",
        response_model=SuccessEnvelope[DashboardSummaryDto],
        operation_id="dashboardGetSummary",
        summary="통합 대시보드 요약 조회",
        description="선택한 시간 범위의 이벤트, Alert, Incident, 엔드포인트와 저장소 지표를 집계해 반환합니다.",
        tags=["Dashboard"],
        responses=_error_responses(400, 401, 503),
    )
    def dashboard_summary(
        request: Request,
        query: Annotated[DashboardSummaryQuery, Query()],
        _user: Annotated[AuthenticatedUser, Depends(current_user)],
    ) -> SuccessEnvelope[DashboardSummaryDto]:
        runtime = _runtime(request)
        calculated_at = datetime.now(UTC)
        from_, to = resolve_time_range(query, now=calculated_at)
        with runtime.postgres() as connection:
            data = _summary_service(runtime, connection).dashboard(
                from_=from_,
                to=to,
                interval=DashboardInterval(query.interval),
                calculated_at=calculated_at,
                endpoint_id=query.endpoint_id,
            )
        return _success(request, data)

    @app.get(
        "/api/v1/dashboard/endpoints/summary",
        response_model=SuccessEnvelope[EndpointSummaryDto],
        operation_id="dashboardGetEndpointSummary",
        summary="엔드포인트 현황 요약 조회",
        description="엔드포인트 상태, 센서 상태, 위험도 분포와 관련 Alert·Incident 지표를 집계합니다.",
        tags=["Dashboard"],
        responses=_error_responses(400, 401, 503),
    )
    def endpoint_summary(
        request: Request,
        query: Annotated[DashboardTimeQuery, Query()],
        _user: Annotated[AuthenticatedUser, Depends(current_user)],
    ) -> SuccessEnvelope[EndpointSummaryDto]:
        runtime = _runtime(request)
        calculated_at = datetime.now(UTC)
        from_, to = resolve_time_range(query, now=calculated_at)
        with runtime.postgres() as connection:
            data = _summary_service(runtime, connection).endpoint_summary(
                from_=from_, to=to, calculated_at=calculated_at, endpoint_id=query.endpoint_id
            )
        return _success(request, data)

    @app.get(
        "/api/v1/dashboard/ingest/summary",
        response_model=SuccessEnvelope[IngestSummaryDto],
        operation_id="dashboardGetIngestSummary",
        summary="수집 파이프라인 요약 조회",
        description="선택한 시간 범위의 수집 이벤트, 저장 상태와 실패 현황을 집계해 반환합니다.",
        tags=["Dashboard"],
        responses=_error_responses(400, 401, 503),
    )
    def ingest_summary(
        request: Request,
        query: Annotated[DashboardTimeQuery, Query()],
        _user: Annotated[AuthenticatedUser, Depends(current_user)],
    ) -> SuccessEnvelope[IngestSummaryDto]:
        runtime = _runtime(request)
        from_, to = resolve_time_range(query, now=datetime.now(UTC))
        with runtime.postgres() as connection:
            data = _summary_service(runtime, connection).ingest_summary(
                from_=from_, to=to, endpoint_id=query.endpoint_id
            )
        return _success(request, data)

    @app.get(
        "/api/v1/dashboard/layouts/{dashboardKey}",
        response_model=SuccessEnvelope[DashboardLayoutDto],
        operation_id="dashboardLayoutsGet",
        summary="대시보드 레이아웃 조회",
        description="현재 사용자가 저장한 대시보드별 위젯 배치와 버전 정보를 조회합니다.",
        tags=["Dashboard"],
        responses=_error_responses(401, 404, 503),
    )
    def dashboard_layout_get(
        request: Request,
        dashboardKey: Annotated[str, Path(description="대시보드를 구분하는 안정적인 키입니다.")],
        user: Annotated[AuthenticatedUser, Depends(current_user)],
    ) -> SuccessEnvelope[DashboardLayoutDto]:
        runtime = _runtime(request)
        with runtime.postgres() as connection:
            data = DashboardLayoutService(DashboardLayoutRepository(connection)).get(
                user_id=user.user_id, dashboard_key=dashboardKey
            )
        return _success(request, data)

    @app.put(
        "/api/v1/dashboard/layouts/{dashboardKey}",
        response_model=SuccessEnvelope[DashboardLayoutDto],
        operation_id="dashboardLayoutsPut",
        summary="대시보드 레이아웃 저장",
        description="현재 사용자의 대시보드 위젯 배치를 생성하거나 기존 버전을 갱신합니다.",
        tags=["Dashboard"],
        responses=_error_responses(400, 401, 404, 409, 503),
    )
    def dashboard_layout_put(
        request: Request,
        dashboardKey: Annotated[str, Path(description="대시보드를 구분하는 안정적인 키입니다.")],
        body: DashboardLayoutPutRequest,
        user: Annotated[AuthenticatedUser, Depends(current_user)],
    ) -> SuccessEnvelope[DashboardLayoutDto]:
        runtime = _runtime(request)
        with runtime.postgres() as connection:
            data = DashboardLayoutService(DashboardLayoutRepository(connection)).put(
                user_id=user.user_id,
                dashboard_key=dashboardKey,
                body=body,
                now=datetime.now(UTC),
            )
        return _success(request, data)

    @app.delete(
        "/api/v1/dashboard/layouts/{dashboardKey}",
        response_model=SuccessEnvelope[DashboardLayoutDto],
        operation_id="dashboardLayoutsDelete",
        summary="대시보드 레이아웃 초기화",
        description="현재 사용자의 저장된 대시보드 레이아웃을 삭제하고 기본 레이아웃 정보를 반환합니다.",
        tags=["Dashboard"],
        responses=_error_responses(401, 404, 503),
    )
    def dashboard_layout_delete(
        request: Request,
        dashboardKey: Annotated[str, Path(description="대시보드를 구분하는 안정적인 키입니다.")],
        user: Annotated[AuthenticatedUser, Depends(current_user)],
    ) -> SuccessEnvelope[DashboardLayoutDto]:
        runtime = _runtime(request)
        with runtime.postgres() as connection:
            data = DashboardLayoutService(DashboardLayoutRepository(connection)).delete(
                user_id=user.user_id, dashboard_key=dashboardKey
            )
        return _success(request, data)

    @app.get(
        "/api/v1/dashboard/topology",
        response_model=SuccessEnvelope[EgressTopologyDto],
        operation_id="dashboardGetTopology",
        summary="외부 통신 토폴로지 조회",
        description="선택한 시간 범위의 엔드포인트와 외부 IP·Domain 통신 관계를 토폴로지로 집계합니다.",
        tags=["Dashboard"],
        responses=_error_responses(400, 401, 503),
    )
    def dashboard_topology(
        request: Request,
        query: Annotated[TopologyQuery, Query()],
        _user: Annotated[AuthenticatedUser, Depends(current_user)],
    ) -> SuccessEnvelope[EgressTopologyDto]:
        runtime = _runtime(request)
        calculated_at = datetime.now(UTC)
        from_, to = resolve_time_range(query, now=calculated_at)
        with runtime.postgres() as connection:
            data = _investigation_service(runtime, connection).topology(
                from_=from_,
                to=to,
                endpoint_ids=query.endpoint_ids,
                calculated_at=calculated_at,
            )
        return _success(request, data)

    @app.get(
        "/api/v1/operations/health",
        response_model=SuccessEnvelope[OperationsHealthDto],
        operation_id="operationsGetHealth",
        summary="운영 구성요소 상태 조회",
        description="PostgreSQL, ClickHouse, Kafka, S3와 파이프라인 워커의 현재 상태를 점검해 반환합니다.",
        tags=["Operations"],
        responses=_error_responses(401),
    )
    def operations_health(
        request: Request,
        _user: Annotated[AuthenticatedUser, Depends(current_user)],
    ) -> SuccessEnvelope[OperationsHealthDto]:
        data = OperationsHealthService(_runtime(request)).snapshot(checked_at=datetime.now(UTC))
        return _success(request, data)

    @app.get(
        "/api/v1/intelligence/forward-dns",
        response_model=SuccessEnvelope[ForwardDnsDto],
        operation_id="intelligenceForwardDns",
        summary="정방향 DNS 조회",
        description="Domain 이름을 DNS로 조회해 확인된 IP 주소와 조회 메타데이터를 반환합니다.",
        tags=["Intelligence"],
        responses=_error_responses(400, 401, 404, 503),
    )
    def intelligence_forward_dns(
        request: Request,
        query: Annotated[ForwardDnsQuery, Query()],
        _user: Annotated[AuthenticatedUser, Depends(current_user)],
    ) -> SuccessEnvelope[ForwardDnsDto]:
        data = _intelligence_service(_runtime(request)).forward(query.domain)
        return _success(request, data)

    @app.get(
        "/api/v1/intelligence/reverse-dns",
        response_model=SuccessEnvelope[ReverseDnsDto],
        operation_id="intelligenceReverseDns",
        summary="역방향 DNS 조회",
        description="IP 주소의 PTR 레코드를 조회해 연결된 Domain 이름을 반환합니다.",
        tags=["Intelligence"],
        responses=_error_responses(400, 401, 404, 503),
    )
    def intelligence_reverse_dns(
        request: Request,
        query: Annotated[ReverseDnsQuery, Query()],
        _user: Annotated[AuthenticatedUser, Depends(current_user)],
    ) -> SuccessEnvelope[ReverseDnsDto]:
        data = _intelligence_service(_runtime(request)).reverse(query.ip)
        return _success(request, data)

    @app.get(
        "/api/v1/intelligence/dns-lookup",
        response_model=SuccessEnvelope[DnsLookupDto],
        operation_id="intelligenceDnsLookup",
        summary="DNS 레코드 조회",
        description="질의값과 레코드 유형을 지정해 DNS 응답, TTL과 조회 메타데이터를 반환합니다.",
        tags=["Intelligence"],
        responses=_error_responses(400, 401, 404, 503),
    )
    def intelligence_dns_lookup(
        request: Request,
        query: Annotated[DnsLookupQuery, Query()],
        _user: Annotated[AuthenticatedUser, Depends(current_user)],
    ) -> SuccessEnvelope[DnsLookupDto]:
        data = _intelligence_service(_runtime(request)).lookup(query.query, query.record_type)
        return _success(request, data)

    @app.get(
        "/api/v1/intelligence/correlate",
        response_model=SuccessEnvelope[CorrelationDto],
        operation_id="intelligenceCorrelate",
        summary="관찰값 상관분석",
        description="IP 또는 Domain 관찰값을 선택한 시간 범위의 이벤트·엔드포인트와 연결해 반환합니다.",
        tags=["Intelligence"],
        responses=_error_responses(400, 401, 503),
    )
    def intelligence_correlate(
        request: Request,
        query: Annotated[CorrelationQuery, Query()],
        _user: Annotated[AuthenticatedUser, Depends(current_user)],
    ) -> SuccessEnvelope[CorrelationDto]:
        runtime = _runtime(request)
        from_, to = resolve_time_range(query, now=datetime.now(UTC))
        data = _intelligence_service(runtime).correlate(
            query.value, from_=from_, to=to, endpoint_ids=query.endpoint_ids
        )
        return _success(request, data)

    @app.post(
        "/api/v1/collector/agents/register",
        response_model=SuccessEnvelope[AgentRegisterData],
        operation_id="collectorRegisterAgent",
        summary="Agent 등록",
        description="mTLS 인증서의 Agent 식별자와 요청 본문을 검증해 Agent를 등록하거나 기존 정보를 갱신합니다.",
        tags=["Collector"],
        responses={
            201: {"model": SuccessEnvelope[AgentRegisterData], "description": "새 Agent를 등록했습니다."},
            **_error_responses(400, 401, 403, 409, 503),
        },
    )
    def register_agent(
        request: Request,
        body: AgentRegisterRequest,
        response: Response,
        identity: Annotated[AgentCertificateIdentity, Depends(trusted_agent_identity)],
        service: Annotated[CollectorService, Depends(get_collector_service)],
    ) -> SuccessEnvelope[AgentRegisterData]:
        data, created = service.register(body, identity, request_id=request.state.request_id)
        response.status_code = 201 if created else 200
        return _success(request, data)

    @app.post(
        "/api/v1/collector/agents/heartbeat",
        response_model=SuccessEnvelope[AgentHeartbeatData],
        operation_id="collectorHeartbeatAgent",
        summary="Agent heartbeat 수신",
        description="mTLS로 인증된 Agent의 센서 상태, 정책 버전과 최근 활동 시각을 갱신합니다.",
        tags=["Collector"],
        responses=_error_responses(400, 401, 403, 503),
    )
    def heartbeat(
        request: Request,
        body: AgentHeartbeatRequest,
        identity: Annotated[AgentCertificateIdentity, Depends(trusted_agent_identity)],
        service: Annotated[CollectorService, Depends(get_collector_service)],
    ) -> SuccessEnvelope[AgentHeartbeatData]:
        return _success(request, service.heartbeat(body, identity))

    @app.post(
        "/api/v1/collector/telemetry/batches",
        response_model=SuccessEnvelope[TelemetryBatchData],
        operation_id="collectorIngestTelemetryBatch",
        summary="텔레메트리 배치 수집",
        description="mTLS로 인증된 Agent가 보낸 이벤트 배치를 검증하고 Kafka 수집 파이프라인에 전달합니다.",
        tags=["Collector"],
        responses=_error_responses(400, 401, 403, 413, 503),
        openapi_extra={
            "requestBody": {
                "required": True,
                "content": {"application/json": {"schema": {"$ref": "#/components/schemas/TelemetryBatchRequest"}}},
            }
        },
    )
    async def telemetry_batch(
        request: Request,
        identity: Annotated[AgentCertificateIdentity, Depends(trusted_agent_identity)],
        service: Annotated[CollectorService, Depends(get_collector_service)],
    ) -> SuccessEnvelope[TelemetryBatchData]:
        if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
            raise RequestValidationError("Content-Type must be application/json.")
        return _success(
            request,
            service.telemetry(
                await request.body(), content_encoding=request.headers.get("content-encoding"), certificate=identity
            ),
        )

    return app


def _openapi_schema(app: FastAPI) -> dict[str, object]:
    if app.openapi_schema is not None:
        return app.openapi_schema
    schema = get_openapi(
        title=app.title,
        version=app.version,
        openapi_version=app.openapi_version,
        description=app.description,
        routes=app.routes,
        tags=app.openapi_tags,
        servers=app.servers,
    )
    components = schema.setdefault("components", {})
    schemas = components.setdefault("schemas", {})
    security_schemes = components.setdefault("securitySchemes", {})
    security_schemes["mutualTLS"] = {
        "type": "mutualTLS",
        "description": "Collector Nginx mTLS 경계에서 검증된 Agent 클라이언트 인증서를 사용합니다.",
    }

    telemetry_schema = TelemetryBatchRequest.model_json_schema(
        by_alias=True,
        mode="validation",
        ref_template="#/components/schemas/{model}",
    )
    schemas.update(telemetry_schema.pop("$defs", {}))
    schemas["TelemetryBatchRequest"] = telemetry_schema
    schemas.pop("HTTPValidationError", None)
    schemas.pop("ValidationError", None)

    for path, path_item in schema["paths"].items():
        for operation in path_item.values():
            if not isinstance(operation, dict) or "responses" not in operation:
                continue
            operation["responses"].pop("422", None)
            success_response = operation["responses"].get("200")
            if isinstance(success_response, dict) and success_response.get("description") == "Successful Response":
                success_response["description"] = "요청을 성공적으로 처리했습니다."
            if path.startswith("/api/v1/collector/"):
                operation["security"] = [{"mutualTLS": []}]
    schema["paths"]["/api/v1/auth/login"]["post"].pop("security", None)
    _remove_null_defaults(schema)
    app.openapi_schema = schema
    return schema


def _remove_null_defaults(value: object) -> None:
    if isinstance(value, dict):
        if value.get("default", object()) is None:
            value.pop("default")
        for nested in value.values():
            _remove_null_defaults(nested)
    elif isinstance(value, list):
        for nested in value:
            _remove_null_defaults(nested)


def _user_dto(row: dict[str, object]) -> UserDto:
    return UserDto(
        user_id=int(row["user_id"]),
        login_id=str(row["login_id"]),
        name=str(row["name"]),
        role=UserRole(row["role"]),
        status=UserStatus(row["status"]),
        locale=UserLocale(row["locale"]),
    )


def _runtime(request: Request) -> RuntimeServices:
    runtime = request.app.state.runtime
    if runtime is None:
        try:
            runtime = RuntimeServices(get_settings())
        except Exception as error:
            raise ServiceUnavailableError("A required dependency is not ready.") from error
        request.app.state.runtime = runtime
    return runtime


def _event_service(runtime: RuntimeServices, connection) -> EventService:
    return EventService(
        events=EventRepository(runtime.clickhouse),
        metadata=IngestMetadataRepository(connection),
        restored=runtime.restored_events,
    )


def _alert_service(runtime: RuntimeServices, connection) -> AlertService:
    return AlertService(
        AlertRepository(connection),
        event_service=_event_service(runtime, connection),
        rules=runtime.rules,
    )


def _summary_service(runtime: RuntimeServices, connection) -> SummaryService:
    return SummaryService(
        endpoints=EndpointRepository(connection),
        alerts=AlertRepository(connection),
        incidents=IncidentRepository(connection),
        metadata=IngestMetadataRepository(connection),
        events=EventRepository(runtime.clickhouse),
        failures=FailureRepository(runtime.clickhouse),
        event_service=_event_service(runtime, connection),
        rules=runtime.rules,
    )


def _investigation_service(runtime: RuntimeServices, connection) -> InvestigationService:
    return InvestigationService(
        endpoints=EndpointRepository(connection),
        alerts=AlertRepository(connection),
        incidents=IncidentRepository(connection),
        events=_event_service(runtime, connection),
    )


def _intelligence_service(runtime: RuntimeServices) -> DnsIntelligenceService:
    return DnsIntelligenceService(events=EventRepository(runtime.clickhouse))


def _success(request: Request, data):
    return SuccessEnvelope(data=data, meta=RequestMeta(request_id=request.state.request_id))


def _error_envelope(request: Request, error: ApplicationError) -> ErrorEnvelope:
    return ErrorEnvelope(
        error=ErrorBody(
            code=error.code,
            message=error.message,
            retryable=error.retryable,
            details=[ErrorDetail.model_validate(detail) for detail in error.details],
        ),
        meta=RequestMeta(request_id=request.state.request_id),
    )


app = create_app()
