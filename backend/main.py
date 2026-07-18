import logging
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID, uuid4

import psycopg
import pyarrow
from botocore.exceptions import BotoCoreError
from clickhouse_connect.driver.exceptions import ClickHouseError
from confluent_kafka import KafkaException
from fastapi import Depends, FastAPI, Query, Request, Response
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
    {"name": "Auth", "description": "Dashboard user authentication."},
    {"name": "Users", "description": "Authenticated dashboard user profile and preferences."},
    {"name": "Endpoints", "description": "Endpoint inventory, health, and Backend-calculated risk."},
    {"name": "Events", "description": "HOT ClickHouse and RESTORED Parquet event evidence."},
    {"name": "Archives", "description": "Archive restore lifecycle operations."},
    {"name": "Alerts", "description": "RuleV1 detections and Alert workflow state."},
    {"name": "Incidents", "description": "Read-only correlated Incident views."},
    {"name": "Dashboard", "description": "Backend-calculated security and collection summaries."},
    {"name": "Operations", "description": "Live dependency and pipeline worker health."},
    {"name": "Intelligence", "description": "DNS lookups and IP/Domain correlation."},
    {"name": "Collector", "description": "mTLS-authenticated Agent registration and telemetry ingest."},
]

ERROR_DESCRIPTIONS = {
    400: "Request validation failed.",
    401: "Authentication failed.",
    403: "The authenticated identity is not permitted to perform this operation.",
    404: "The requested resource was not found.",
    409: "The request conflicts with the current resource, identity, or Archive state.",
    413: "The request body or event count exceeds the documented limit.",
    429: "The request exceeded the configured rate limit.",
    503: "A required dependency is temporarily unavailable.",
}

BEARER = HTTPBearer(
    auto_error=False,
    scheme_name="BearerJWT",
    description="JWT access token returned by POST /api/v1/auth/login.",
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
        title="EDR_C",
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
        tags=["Endpoints"],
        responses=_error_responses(400, 401, 404, 503),
    )
    def endpoint_detail(
        endpointId: int,
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
        tags=["Endpoints"],
        responses=_error_responses(400, 401, 503),
    )
    def endpoint_process_tree(
        endpointId: int,
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
        tags=["Events"],
        responses=_error_responses(400, 401, 404, 409, 503),
    )
    def event_detail(
        eventId: UUID,
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
        tags=["Archives"],
        responses={
            202: {"model": SuccessEnvelope[ArchiveRestoreStartDto], "description": "Restore accepted."},
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
        tags=["Alerts"],
        responses=_error_responses(400, 401, 404, 503),
    )
    def alert_detail(
        alertId: int,
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
        tags=["Alerts"],
        responses=_error_responses(400, 401, 403, 404, 503),
    )
    def alert_status(
        alertId: int,
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
        tags=["Incidents"],
        responses=_error_responses(400, 401, 404, 503),
    )
    def incident_detail(
        incidentId: int,
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
        tags=["Incidents"],
        responses=_error_responses(400, 401, 404, 503),
    )
    def incident_timeline(
        incidentId: int,
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
        tags=["Incidents"],
        responses=_error_responses(400, 401, 404, 503),
    )
    def incident_investigation(
        incidentId: int,
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
        tags=["Dashboard"],
        responses=_error_responses(401, 404, 503),
    )
    def dashboard_layout_get(
        request: Request,
        dashboardKey: str,
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
        tags=["Dashboard"],
        responses=_error_responses(400, 401, 404, 409, 503),
    )
    def dashboard_layout_put(
        request: Request,
        dashboardKey: str,
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
        tags=["Dashboard"],
        responses=_error_responses(401, 404, 503),
    )
    def dashboard_layout_delete(
        request: Request,
        dashboardKey: str,
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
        tags=["Collector"],
        responses={
            201: {"model": SuccessEnvelope[AgentRegisterData], "description": "Agent created."},
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
        "description": "Agent certificate validated by the Collector Nginx mTLS boundary.",
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
