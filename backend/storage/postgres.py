from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from backend.contracts.auth import normalize_login_id
from backend.contracts.collector import AgentHeartbeatRequest, AgentRegisterRequest
from backend.contracts.enums import (
    AlertSortBy,
    AlertStatus,
    EndpointStatus,
    IncidentStatus,
    OsType,
    RiskLevel,
    UserLocale,
    UserRole,
    UserStatus,
)
from backend.errors import (
    AgentIdentityConflictError,
    ArchivedDayImmutableError,
    EndpointRetiredError,
    InvalidAgentCertificateError,
)

from .models import (
    AgentCertificateIdentity,
    AgentRegistrationResult,
    AlertInsert,
    EndpointAuthContext,
    EndpointInsert,
    IncidentInsert,
    IngestBucket,
    StoredAlert,
    StoredIncident,
)


def _escape_like_prefix(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def _alert_order_by(sort_by: AlertSortBy, sort_order: str) -> str:
    sort_by = AlertSortBy(sort_by)
    if sort_by is AlertSortBy.PRIORITY:
        return (
            "CASE status WHEN 'OPEN' THEN 0 WHEN 'IN_PROGRESS' THEN 1 ELSE 2 END ASC, "
            "CASE severity WHEN 'CRITICAL' THEN 0 WHEN 'HIGH' THEN 1 WHEN 'MEDIUM' THEN 2 ELSE 3 END ASC, "
            "risk_score DESC, detected_at DESC, alert_id ASC"
        )

    direction = "ASC" if sort_order == "asc" else "DESC"
    expression = {
        AlertSortBy.DETECTED_AT: "detected_at",
        AlertSortBy.SEVERITY: ("CASE severity WHEN 'LOW' THEN 0 WHEN 'MEDIUM' THEN 1 WHEN 'HIGH' THEN 2 ELSE 3 END"),
        AlertSortBy.RISK_SCORE: "risk_score",
        AlertSortBy.STATUS: ("CASE status WHEN 'RESOLVED' THEN 0 WHEN 'IN_PROGRESS' THEN 1 ELSE 2 END"),
    }[sort_by]
    return f"{expression} {direction}, alert_id ASC"


class UserRepository:
    def __init__(self, connection: Connection[Any]) -> None:
        self.connection = connection

    def create_admin(self, *, login_id: str, name: str, password_hash: str, now: datetime) -> int:
        try:
            row = self.connection.execute(
                """
                INSERT INTO users (login_id, password_hash, name, role, status, created_at, updated_at)
                VALUES (%s, %s, %s, 'ADMIN', 'ACTIVE', %s, %s)
                RETURNING user_id
                """,
                (normalize_login_id(login_id), password_hash, name, now, now),
            ).fetchone()
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise
        if row is None:
            raise RuntimeError("ADMIN creation failed")
        return int(row[0])

    def reset_admin_credentials(self, *, login_id: str, name: str, password_hash: str, now: datetime) -> int | None:
        try:
            row = self.connection.execute(
                """
                UPDATE users
                SET password_hash = %s, name = %s, role = 'ADMIN', status = 'ACTIVE', updated_at = %s
                WHERE LOWER(login_id) = %s AND is_delete = FALSE
                RETURNING user_id
                """,
                (password_hash, name, now, normalize_login_id(login_id)),
            ).fetchone()
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise
        return int(row[0]) if row is not None else None

    def by_login_id(self, login_id: str) -> dict[str, Any] | None:
        with self.connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT user_id, login_id, password_hash, name, role, status, locale
                FROM users WHERE LOWER(login_id) = %s AND is_delete = FALSE
                """,
                (normalize_login_id(login_id),),
            )
            row = cursor.fetchone()
        return dict(row) if row is not None else None

    def by_user_id(self, user_id: int) -> dict[str, Any] | None:
        with self.connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT user_id, login_id, name, role, status, locale
                FROM users
                WHERE user_id = %s AND status = 'ACTIVE' AND is_delete = FALSE
                """,
                (user_id,),
            )
            row = cursor.fetchone()
        return dict(row) if row is not None else None

    def update_locale(
        self,
        *,
        user_id: int,
        locale: UserLocale,
        request_id: str,
        changed_at: datetime,
    ) -> dict[str, Any] | None:
        with self.connection.transaction():
            with self.connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    """
                    SELECT user_id, login_id, name, role, status, locale
                    FROM users
                    WHERE user_id = %s AND status = 'ACTIVE' AND is_delete = FALSE
                    FOR UPDATE
                    """,
                    (user_id,),
                )
                current = cursor.fetchone()
                if current is None:
                    return None
                if current["locale"] == locale.value:
                    return dict(current)
                cursor.execute(
                    """
                    UPDATE users
                    SET locale = %s, updated_at = %s
                    WHERE user_id = %s AND status = 'ACTIVE' AND is_delete = FALSE
                    RETURNING user_id, login_id, name, role, status, locale
                    """,
                    (locale.value, changed_at, user_id),
                )
                updated = cursor.fetchone()
                if updated is None:
                    return None
                cursor.execute(
                    """
                    INSERT INTO audit_logs (
                        actor_type, actor_identifier, action, resource_type, resource_id,
                        before_json, after_json, request_id, created_at
                    ) VALUES (
                        'USER', %s, 'USER_LOCALE_CHANGED', 'USER', %s,
                        jsonb_build_object('locale', %s::text),
                        jsonb_build_object('locale', %s::text), %s, %s
                    )
                    """,
                    (
                        str(user_id),
                        str(user_id),
                        current["locale"],
                        locale.value,
                        request_id,
                        changed_at,
                    ),
                )
        return dict(updated)

    def active_identity(self, user_id: int) -> tuple[UserRole, UserStatus] | None:
        row = self.connection.execute(
            "SELECT role, status FROM users WHERE user_id = %s AND is_delete = FALSE",
            (user_id,),
        ).fetchone()
        if row is None:
            return None
        return UserRole(row[0]), UserStatus(row[1])


class DashboardLayoutRepository:
    def __init__(self, connection: Connection[Any]) -> None:
        self.connection = connection

    def get(self, user_id: int, dashboard_key: str) -> dict[str, Any] | None:
        with self.connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT layout_id, user_id, dashboard_key, layout_version, revision, layout_json,
                       created_at, updated_at
                FROM user_dashboard_layouts
                WHERE user_id = %s AND dashboard_key = %s
                """,
                (user_id, dashboard_key),
            )
            row = cursor.fetchone()
        return dict(row) if row is not None else None

    def upsert(
        self,
        *,
        user_id: int,
        dashboard_key: str,
        layout_version: int,
        expected_revision: int,
        widgets: list[dict[str, object]],
        now: datetime,
    ) -> int | None:
        try:
            row = self.connection.execute(
                """
                WITH input (
                    user_id, dashboard_key, layout_version, expected_revision, layout_json, changed_at
                ) AS (
                    VALUES (%s, %s, %s, %s, %s, %s)
                ), updated AS (
                    UPDATE user_dashboard_layouts AS stored
                    SET layout_version = input.layout_version,
                        revision = stored.revision + 1,
                        layout_json = input.layout_json,
                        updated_at = input.changed_at
                    FROM input
                    WHERE stored.user_id = input.user_id
                      AND stored.dashboard_key = input.dashboard_key
                      AND stored.revision = input.expected_revision
                    RETURNING stored.revision
                ), inserted AS (
                    INSERT INTO user_dashboard_layouts (
                        user_id, dashboard_key, layout_version, revision, layout_json, created_at, updated_at
                    )
                    SELECT input.user_id, input.dashboard_key, input.layout_version, 1,
                           input.layout_json, input.changed_at, input.changed_at
                    FROM input
                    WHERE input.expected_revision = 0
                      AND NOT EXISTS (
                          SELECT 1 FROM user_dashboard_layouts AS stored
                          WHERE stored.user_id = input.user_id
                            AND stored.dashboard_key = input.dashboard_key
                      )
                    ON CONFLICT (user_id, dashboard_key) DO NOTHING
                    RETURNING revision
                )
                SELECT revision FROM updated
                UNION ALL
                SELECT revision FROM inserted
                LIMIT 1
                """,
                (
                    user_id,
                    dashboard_key,
                    layout_version,
                    expected_revision,
                    Jsonb(widgets),
                    now,
                ),
            ).fetchone()
            if row is None:
                self.connection.rollback()
                return None
            self.connection.commit()
            return int(row[0])
        except Exception:
            self.connection.rollback()
            raise

    def delete(self, user_id: int, dashboard_key: str) -> None:
        try:
            self.connection.execute(
                "DELETE FROM user_dashboard_layouts WHERE user_id = %s AND dashboard_key = %s",
                (user_id, dashboard_key),
            )
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise


class EndpointRepository:
    def __init__(self, connection: Connection[Any]) -> None:
        self.connection = connection

    def insert(self, endpoint: EndpointInsert) -> int:
        now = endpoint.registered_at.astimezone(UTC)
        row = self.connection.execute(
            """
            INSERT INTO endpoints (
                agent_id, hostname, os_type, capability_codes_json, sensor_health_json,
                registered_at, status, last_seen_at, created_at, updated_at
            ) VALUES (%s, %s, %s, '[]'::jsonb, '[]'::jsonb, %s, 'ONLINE', %s, %s, %s)
            ON CONFLICT (agent_id) DO UPDATE SET
                hostname = EXCLUDED.hostname,
                updated_at = EXCLUDED.updated_at
            WHERE endpoints.is_delete = FALSE AND endpoints.status <> 'RETIRED'
            RETURNING endpoint_id
            """,
            (endpoint.agent_id, endpoint.hostname, endpoint.os_type.value, now, now, now, now),
        ).fetchone()
        if row is None:
            raise ValueError("endpoint is retired or unavailable")
        self.connection.commit()
        return int(row[0])

    def register_agent(
        self,
        request: AgentRegisterRequest,
        certificate: AgentCertificateIdentity,
        *,
        received_at: datetime,
        request_id: str,
    ) -> AgentRegistrationResult:
        if request.agent_id != certificate.san_agent_id:
            raise AgentIdentityConflictError("Request agentId does not match certificate SAN identity.")
        fingerprint = certificate.fingerprint_sha256.lower()
        with self.connection.transaction():
            with self.connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    "SELECT endpoint_id FROM agent_auth_keys WHERE cert_fingerprint = %s",
                    (fingerprint,),
                )
                fingerprint_owner = cursor.fetchone()
                cursor.execute(
                    "SELECT * FROM endpoints WHERE agent_id = %s AND is_delete = FALSE FOR UPDATE",
                    (request.agent_id,),
                )
                endpoint = cursor.fetchone()

            if endpoint is None:
                if fingerprint_owner is not None:
                    raise AgentIdentityConflictError("Certificate fingerprint belongs to another Endpoint.")
                row = self.connection.execute(
                    """
                    INSERT INTO endpoints (
                        agent_id, hostname, os_type, os_version, agent_version, agent_build_id, agent_arch,
                        capability_codes_json, sensor_health_json, registered_at, status, last_seen_at,
                        created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, '[]'::jsonb, %s, 'ONLINE', %s, %s, %s)
                    RETURNING endpoint_id, registered_at
                    """,
                    (
                        request.agent_id,
                        request.hostname,
                        request.os_type.value,
                        request.os_version,
                        request.agent_version,
                        request.agent_build_id,
                        request.agent_arch.value,
                        Jsonb(request.capability_codes),
                        received_at,
                        received_at,
                        received_at,
                        received_at,
                    ),
                ).fetchone()
                if row is None:
                    raise RuntimeError("Endpoint registration failed")
                endpoint_id = int(row[0])
                self._insert_certificate(endpoint_id, certificate, fingerprint, received_at)
                return AgentRegistrationResult(endpoint_id, request.agent_id, EndpointStatus.ONLINE, row[1], True)

            endpoint_id = int(endpoint["endpoint_id"])
            if endpoint["status"] == EndpointStatus.RETIRED.value:
                raise EndpointRetiredError()
            if fingerprint_owner is not None and int(fingerprint_owner["endpoint_id"]) != endpoint_id:
                raise AgentIdentityConflictError("Certificate fingerprint belongs to another Endpoint.")

            active = self.connection.execute(
                """
                SELECT cert_fingerprint FROM agent_auth_keys
                WHERE endpoint_id = %s AND is_delete = FALSE AND revoked_at IS NULL
                FOR UPDATE
                """,
                (endpoint_id,),
            ).fetchone()
            same_certificate = active is not None and str(active[0]).lower() == fingerprint
            if not same_certificate:
                if fingerprint_owner is not None:
                    raise AgentIdentityConflictError("A revoked certificate cannot be reactivated.")
                self.connection.execute(
                    """
                    UPDATE agent_auth_keys SET revoked_at = %s, updated_at = %s
                    WHERE endpoint_id = %s AND is_delete = FALSE AND revoked_at IS NULL
                    """,
                    (received_at, received_at, endpoint_id),
                )
                self._insert_certificate(endpoint_id, certificate, fingerprint, received_at)
                if active is not None:
                    self.connection.execute(
                        """
                        INSERT INTO audit_logs (
                            actor_type, actor_identifier, action, resource_type, resource_id,
                            before_json, after_json, request_id, created_at
                        ) VALUES (
                            'AGENT', %s, 'AGENT_CERTIFICATE_ROTATED', 'AGENT_AUTH_KEY', %s,
                            jsonb_build_object('fingerprint', %s::text),
                            jsonb_build_object('fingerprint', %s::text), %s, %s
                        )
                        """,
                        (request.agent_id, str(endpoint_id), active[0], fingerprint, request_id, received_at),
                    )

            self.connection.execute(
                """
                UPDATE endpoints SET
                    hostname = %s, os_type = %s, os_version = %s, agent_version = %s,
                    agent_build_id = %s, agent_arch = %s, capability_codes_json = %s,
                    status = 'ONLINE', last_seen_at = %s, updated_at = %s
                WHERE endpoint_id = %s
                """,
                (
                    request.hostname,
                    request.os_type.value,
                    request.os_version,
                    request.agent_version,
                    request.agent_build_id,
                    request.agent_arch.value,
                    Jsonb(request.capability_codes),
                    received_at,
                    received_at,
                    endpoint_id,
                ),
            )
            return AgentRegistrationResult(
                endpoint_id, request.agent_id, EndpointStatus.ONLINE, endpoint["registered_at"], False
            )

    def _insert_certificate(
        self,
        endpoint_id: int,
        certificate: AgentCertificateIdentity,
        fingerprint: str,
        now: datetime,
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO agent_auth_keys (
                endpoint_id, cert_fingerprint, cert_subject, cert_san_agent_id,
                issued_at, expires_at, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                endpoint_id,
                fingerprint,
                certificate.subject,
                certificate.san_agent_id,
                certificate.issued_at,
                certificate.expires_at,
                now,
                now,
            ),
        )

    def authenticate_agent(
        self,
        agent_id: str,
        certificate: AgentCertificateIdentity,
        *,
        now: datetime,
    ) -> EndpointAuthContext:
        if agent_id != certificate.san_agent_id:
            raise InvalidAgentCertificateError()
        with self.connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                "SELECT * FROM endpoints WHERE agent_id = %s AND is_delete = FALSE",
                (agent_id,),
            )
            endpoint = cursor.fetchone()
            if endpoint is None:
                raise InvalidAgentCertificateError()
            if endpoint["status"] == EndpointStatus.RETIRED.value:
                raise EndpointRetiredError()
            cursor.execute(
                """
                SELECT 1 FROM agent_auth_keys
                WHERE endpoint_id = %s AND cert_fingerprint = %s
                  AND cert_san_agent_id = %s AND is_delete = FALSE AND revoked_at IS NULL
                  AND issued_at <= %s AND expires_at > %s
                """,
                (
                    endpoint["endpoint_id"],
                    certificate.fingerprint_sha256.lower(),
                    certificate.san_agent_id,
                    now,
                    now,
                ),
            )
            if cursor.fetchone() is None:
                raise InvalidAgentCertificateError()
            return EndpointAuthContext(
                endpoint_id=int(endpoint["endpoint_id"]),
                agent_id=str(endpoint["agent_id"]),
                hostname=str(endpoint["hostname"]),
                os_type=OsType(endpoint["os_type"]),
                ip_address=str(endpoint["ip_address"]) if endpoint["ip_address"] is not None else None,
            )

    def heartbeat(
        self,
        endpoint_id: int,
        request: AgentHeartbeatRequest,
        *,
        received_at: datetime,
    ) -> None:
        with self.connection.transaction():
            cursor = self.connection.execute(
                """
                UPDATE endpoints SET
                    agent_version = %s, agent_build_id = %s, agent_arch = %s,
                    capability_codes_json = %s, sensor_health_json = %s,
                    status = 'ONLINE', last_seen_at = %s, updated_at = %s
                WHERE endpoint_id = %s AND is_delete = FALSE AND status <> 'RETIRED'
                """,
                (
                    request.agent_version,
                    request.agent_build_id,
                    request.agent_arch.value,
                    Jsonb(request.capability_codes),
                    Jsonb(
                        [
                            item.model_dump(mode="json", by_alias=True, exclude_unset=True)
                            for item in request.sensor_health
                        ]
                    ),
                    received_at,
                    received_at,
                    endpoint_id,
                ),
            )
            if cursor.rowcount != 1:
                raise EndpointRetiredError()

    def mark_offline(self, *, cutoff: datetime, updated_at: datetime) -> int:
        with self.connection.transaction():
            cursor = self.connection.execute(
                """
                UPDATE endpoints SET status = 'OFFLINE', updated_at = %s
                WHERE is_delete = FALSE AND status <> 'RETIRED'
                  AND last_seen_at < %s AND status <> 'OFFLINE'
                """,
                (updated_at, cutoff),
            )
            return int(cursor.rowcount)

    def risk_snapshot(
        self,
        *,
        endpoint_ids: Sequence[int] | None = None,
        q: str | None = None,
        status: str | None = None,
        os_type: OsType | None = None,
    ) -> list[dict[str, Any]]:
        query_endpoint_id: int | None = None
        query_prefix: str | None = None
        if q is not None:
            if q.isdecimal():
                query_endpoint_id = int(q)
            else:
                query_prefix = _escape_like_prefix(q.lower())
        with self.connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                WITH candidate_endpoints AS (
                    SELECT e.* FROM endpoints e
                    WHERE e.is_delete = FALSE
                      AND (%s::bigint[] IS NULL OR e.endpoint_id = ANY(%s::bigint[]))
                      AND (%s::text IS NULL OR e.status = %s::text)
                      AND (%s::text IS NULL OR e.os_type = %s::text)
                      AND (
                          %s::text IS NULL
                          OR (%s::bigint IS NOT NULL AND e.endpoint_id = %s::bigint)
                          OR (
                              %s::text IS NOT NULL
                              AND (
                                  LOWER(e.hostname) LIKE %s::text ESCAPE E'\\\\'
                                  OR LOWER(e.agent_id) LIKE %s::text ESCAPE E'\\\\'
                              )
                          )
                      )
                ), active_alerts AS (
                    SELECT endpoint_id,
                           jsonb_agg(jsonb_build_object(
                               'alert_id', alert_id, 'rule_code', rule_code, 'rule_version', rule_version,
                               'risk_score', risk_score, 'detected_at', detected_at, 'title', title,
                               'severity', severity
                           ) ORDER BY risk_score DESC, detected_at DESC, alert_id DESC) AS items
                    FROM alerts
                    WHERE is_delete = FALSE AND status IN ('OPEN', 'IN_PROGRESS')
                      AND endpoint_id IN (SELECT endpoint_id FROM candidate_endpoints)
                    GROUP BY endpoint_id
                ), open_incidents AS (
                    SELECT endpoint_id,
                           jsonb_agg(jsonb_build_object(
                               'incident_id', incident_id, 'title', title, 'severity', severity,
                               'last_detected_at', last_detected_at
                           ) ORDER BY last_detected_at DESC, incident_id DESC) AS items
                    FROM incidents
                    WHERE is_delete = FALSE AND status = 'OPEN'
                      AND endpoint_id IN (SELECT endpoint_id FROM candidate_endpoints)
                    GROUP BY endpoint_id
                )
                SELECT e.*, COALESCE(a.items, '[]'::jsonb) AS active_alerts,
                       COALESCE(i.items, '[]'::jsonb) AS open_incidents
                FROM candidate_endpoints e
                LEFT JOIN active_alerts a ON a.endpoint_id = e.endpoint_id
                LEFT JOIN open_incidents i ON i.endpoint_id = e.endpoint_id
                """,
                (
                    list(endpoint_ids) if endpoint_ids else None,
                    list(endpoint_ids) if endpoint_ids else None,
                    status,
                    status,
                    os_type.value if os_type else None,
                    os_type.value if os_type else None,
                    q,
                    query_endpoint_id,
                    query_endpoint_id,
                    query_prefix,
                    query_prefix,
                    query_prefix,
                ),
            )
            return [dict(row) for row in cursor.fetchall()]

    def risk_page(
        self,
        *,
        endpoint_ids: Sequence[int] | None = None,
        q: str | None = None,
        status: str | None = None,
        os_type: OsType | None = None,
        risk_level: RiskLevel | None = None,
        sort_by: str = "riskScore",
        sort_order: str = "desc",
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        query_endpoint_id: int | None = None
        query_prefix: str | None = None
        if q is not None:
            if q.isdecimal():
                query_endpoint_id = int(q)
            else:
                query_prefix = _escape_like_prefix(q.lower())

        direction = "ASC" if sort_order == "asc" else "DESC"
        if q is not None:
            order_by = (
                "CASE WHEN LOWER(hostname) = %s OR LOWER(agent_id) = %s THEN 0 ELSE 1 END ASC, "
                "CASE status WHEN 'ONLINE' THEN 0 WHEN 'OFFLINE' THEN 1 ELSE 2 END ASC, "
                "calculated_risk_score DESC, LOWER(hostname) ASC, endpoint_id ASC"
            )
            order_parameters: tuple[Any, ...] = (q.lower(), q.lower())
        elif sort_by == "lastSeenAt":
            nulls = "FIRST" if direction == "ASC" else "LAST"
            order_by = f"last_seen_at {direction} NULLS {nulls}, endpoint_id ASC"
            order_parameters = ()
        elif sort_by == "registeredAt":
            order_by = f"registered_at {direction}, endpoint_id ASC"
            order_parameters = ()
        else:
            order_by = f"calculated_risk_score {direction}, endpoint_id ASC"
            order_parameters = ()

        risk_condition = {
            None: "TRUE",
            RiskLevel.LOW: "calculated_risk_score < 25",
            RiskLevel.MEDIUM: "calculated_risk_score BETWEEN 25 AND 49",
            RiskLevel.HIGH: "calculated_risk_score BETWEEN 50 AND 79",
            RiskLevel.CRITICAL: "calculated_risk_score >= 80",
        }[risk_level]
        sql = f"""
            WITH candidate_endpoints AS (
                SELECT e.* FROM endpoints e
                WHERE e.is_delete = FALSE
                  AND (%s::bigint[] IS NULL OR e.endpoint_id = ANY(%s::bigint[]))
                  AND (%s::text IS NULL OR e.status = %s::text)
                  AND (%s::text IS NULL OR e.os_type = %s::text)
                  AND (
                      %s::text IS NULL
                      OR (%s::bigint IS NOT NULL AND e.endpoint_id = %s::bigint)
                      OR (
                          %s::text IS NOT NULL
                          AND (
                              LOWER(e.hostname) LIKE %s::text ESCAPE E'\\\\'
                              OR LOWER(e.agent_id) LIKE %s::text ESCAPE E'\\\\'
                          )
                      )
                  )
            ), active_alert_candidates AS (
                SELECT a.*,
                       row_number() OVER (
                           PARTITION BY endpoint_id, rule_code, rule_version
                           ORDER BY risk_score DESC, detected_at DESC, alert_id DESC
                       ) AS representative_rank
                FROM alerts a
                WHERE a.is_delete = FALSE AND a.status IN ('OPEN', 'IN_PROGRESS')
                  AND a.endpoint_id IN (SELECT endpoint_id FROM candidate_endpoints)
            ), representative_alerts AS (
                SELECT candidates.*,
                       row_number() OVER (
                           PARTITION BY endpoint_id
                           ORDER BY risk_score DESC, detected_at DESC, alert_id DESC
                       ) AS risk_rank
                FROM active_alert_candidates candidates
                WHERE representative_rank = 1
            ), alert_risk AS (
                SELECT endpoint_id,
                       jsonb_agg(jsonb_build_object(
                           'alert_id', alert_id, 'rule_code', rule_code, 'rule_version', rule_version,
                           'risk_score', risk_score, 'detected_at', detected_at, 'title', title,
                           'severity', severity
                       ) ORDER BY risk_rank) FILTER (WHERE risk_rank <= 3) AS items,
                       SUM(CASE risk_rank
                           WHEN 1 THEN ROUND(risk_score)
                           WHEN 2 THEN ROUND(risk_score * 0.25)
                           WHEN 3 THEN ROUND(risk_score * 0.10)
                           ELSE 0
                       END) AS contribution
                FROM representative_alerts
                GROUP BY endpoint_id
            ), alert_counts AS (
                SELECT a.endpoint_id, COUNT(*) AS active_alert_count,
                       MAX(a.risk_score) AS highest_alert_risk_score
                FROM alerts a
                WHERE a.is_delete = FALSE AND a.status IN ('OPEN', 'IN_PROGRESS')
                  AND a.endpoint_id IN (SELECT endpoint_id FROM candidate_endpoints)
                GROUP BY a.endpoint_id
            ), ranked_incidents AS (
                SELECT i.*,
                       row_number() OVER (
                           PARTITION BY endpoint_id
                           ORDER BY CASE severity
                               WHEN 'CRITICAL' THEN 3 WHEN 'HIGH' THEN 2
                               WHEN 'MEDIUM' THEN 1 ELSE 0
                           END DESC, last_detected_at DESC, incident_id DESC
                       ) AS risk_rank
                FROM incidents i
                WHERE i.is_delete = FALSE AND i.status = 'OPEN'
                  AND i.endpoint_id IN (SELECT endpoint_id FROM candidate_endpoints)
            ), incident_risk AS (
                SELECT endpoint_id,
                       jsonb_agg(jsonb_build_object(
                           'incident_id', incident_id, 'title', title, 'severity', severity,
                           'last_detected_at', last_detected_at
                       ) ORDER BY risk_rank) FILTER (WHERE risk_rank <= 2) AS items,
                       COUNT(*) AS open_incident_count
                FROM ranked_incidents
                GROUP BY endpoint_id
            ), scored_endpoints AS (
                SELECT e.*, COALESCE(ar.items, '[]'::jsonb) AS active_alerts,
                       COALESCE(ir.items, '[]'::jsonb) AS open_incidents,
                       COALESCE(ac.active_alert_count, 0) AS active_alert_count,
                       COALESCE(ir.open_incident_count, 0) AS open_incident_count,
                       ac.highest_alert_risk_score,
                       LEAST(
                           100,
                           COALESCE(ar.contribution, 0) + LEAST(COALESCE(ir.open_incident_count, 0), 2) * 10
                       )::integer AS calculated_risk_score
                FROM candidate_endpoints e
                LEFT JOIN alert_risk ar ON ar.endpoint_id = e.endpoint_id
                LEFT JOIN alert_counts ac ON ac.endpoint_id = e.endpoint_id
                LEFT JOIN incident_risk ir ON ir.endpoint_id = e.endpoint_id
            )
            SELECT *, COUNT(*) OVER() AS total_count
            FROM scored_endpoints
            WHERE {risk_condition}
            ORDER BY {order_by}
            LIMIT %s OFFSET %s
        """
        base_parameters: tuple[Any, ...] = (
            list(endpoint_ids) if endpoint_ids else None,
            list(endpoint_ids) if endpoint_ids else None,
            status,
            status,
            os_type.value if os_type else None,
            os_type.value if os_type else None,
            q,
            query_endpoint_id,
            query_endpoint_id,
            query_prefix,
            query_prefix,
            query_prefix,
        )

        def fetch(page_limit: int, page_offset: int) -> list[dict[str, Any]]:
            with self.connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(sql, base_parameters + order_parameters + (page_limit, page_offset))
                return [dict(row) for row in cursor.fetchall()]

        rows = fetch(limit, offset)
        if rows:
            total = int(rows[0].pop("total_count"))
            for row in rows[1:]:
                row.pop("total_count", None)
            return rows, total
        if offset:
            first = fetch(1, 0)
            return [], int(first[0]["total_count"]) if first else 0
        return [], 0

    def certificates(self, endpoint_id: int) -> list[dict[str, Any]]:
        with self.connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT cert_fingerprint, cert_subject, cert_san_agent_id, issued_at, expires_at, revoked_at
                FROM agent_auth_keys
                WHERE endpoint_id = %s AND is_delete = FALSE
                ORDER BY issued_at DESC, agent_auth_key_id DESC
                """,
                (endpoint_id,),
            )
            return [dict(row) for row in cursor.fetchall()]


class AlertRepository:
    def __init__(self, connection: Connection[Any]) -> None:
        self.connection = connection

    def insert_if_absent(self, alert: AlertInsert) -> StoredAlert:
        now = alert.detected_at.astimezone(UTC)
        with self.connection.transaction():
            row = self.connection.execute(
                """
                INSERT INTO alerts (
                    endpoint_id, event_id, event_occurred_at, batch_id, agent_id,
                    rule_code, rule_name, rule_version,
                    mitre_tactic_code, mitre_tactic_name, mitre_technique_code, mitre_technique_name,
                    title, summary, severity, risk_score, status, detected_at, created_at, updated_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, 'OPEN', %s, %s, %s
                )
                ON CONFLICT (event_id, rule_code, rule_version) DO NOTHING
                RETURNING alert_id, status
                """,
                (
                    alert.endpoint_id,
                    alert.event_id,
                    alert.event_occurred_at,
                    alert.batch_id,
                    alert.agent_id,
                    alert.rule_code,
                    alert.rule_name,
                    alert.rule_version,
                    alert.mitre_tactic_code,
                    alert.mitre_tactic_name,
                    alert.mitre_technique_code,
                    alert.mitre_technique_name,
                    alert.title,
                    alert.summary,
                    alert.severity.value,
                    alert.risk_score,
                    now,
                    now,
                    now,
                ),
            ).fetchone()
            if row is not None:
                return StoredAlert(int(row[0]), True, AlertStatus(row[1]))
            existing = self.connection.execute(
                """
                SELECT alert_id, status FROM alerts
                WHERE event_id = %s AND rule_code = %s AND rule_version = %s AND is_delete = FALSE
                """,
                (alert.event_id, alert.rule_code, alert.rule_version),
            ).fetchone()
            if existing is None:
                raise RuntimeError("alert idempotency lookup failed")
            return StoredAlert(int(existing[0]), False, AlertStatus(existing[1]))

    def update_status_with_audit(
        self,
        *,
        alert_id: int,
        status: AlertStatus,
        actor_identifier: str,
        request_id: str,
        changed_at: datetime,
    ) -> dict[str, Any]:
        with self.connection.transaction():
            with self.connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute("SELECT * FROM alerts WHERE alert_id = %s AND is_delete = FALSE FOR UPDATE", (alert_id,))
                before = cursor.fetchone()
            if before is None:
                raise KeyError(alert_id)
            if before["status"] != status.value:
                self.connection.execute(
                    "UPDATE alerts SET status = %s, updated_at = %s WHERE alert_id = %s",
                    (status.value, changed_at, alert_id),
                )
                self.connection.execute(
                    """
                    INSERT INTO audit_logs (
                        actor_type, actor_identifier, action, resource_type, resource_id,
                        before_json, after_json, request_id, created_at
                    ) VALUES (
                        'USER', %s, 'ALERT_STATUS_CHANGED', 'ALERT', %s,
                        jsonb_build_object('status', %s::text),
                        jsonb_build_object('status', %s::text), %s, %s
                    )
                    """,
                    (
                        actor_identifier,
                        str(alert_id),
                        before["status"],
                        status.value,
                        request_id,
                        changed_at,
                    ),
                )
                before["status"] = status.value
                before["updated_at"] = changed_at
            return dict(before)

    def list_rows(
        self,
        *,
        from_: datetime,
        to: datetime,
        endpoint_id: int | None = None,
        status: AlertStatus | None = None,
        severity: str | None = None,
        rule_code: str | None = None,
        sort_by: AlertSortBy = AlertSortBy.PRIORITY,
        sort_order: str = "desc",
        limit: int | None = None,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        order_by = _alert_order_by(sort_by, sort_order)
        pagination = " LIMIT %s OFFSET %s" if limit is not None else ""
        query = f"""
            SELECT * FROM alerts
            WHERE is_delete = FALSE AND detected_at >= %s AND detected_at < %s
              AND (%s::bigint IS NULL OR endpoint_id = %s::bigint)
              AND (%s::text IS NULL OR status = %s::text)
              AND (%s::text IS NULL OR severity = %s::text)
              AND (%s::text IS NULL OR rule_code = %s::text)
            ORDER BY {order_by}{pagination}
        """
        values: tuple[Any, ...] = (
            from_,
            to,
            endpoint_id,
            endpoint_id,
            status.value if status else None,
            status.value if status else None,
            severity,
            severity,
            rule_code,
            rule_code,
        )
        if limit is not None:
            values += (limit, offset)
        with self.connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(query, values)
            return [dict(row) for row in cursor.fetchall()]

    def count_rows(
        self,
        *,
        from_: datetime,
        to: datetime,
        endpoint_id: int | None = None,
        status: AlertStatus | None = None,
        severity: str | None = None,
        rule_code: str | None = None,
    ) -> int:
        row = self.connection.execute(
            """
            SELECT count(*) FROM alerts
            WHERE is_delete = FALSE AND detected_at >= %s AND detected_at < %s
              AND (%s::bigint IS NULL OR endpoint_id = %s::bigint)
              AND (%s::text IS NULL OR status = %s::text)
              AND (%s::text IS NULL OR severity = %s::text)
              AND (%s::text IS NULL OR rule_code = %s::text)
            """,
            (
                from_,
                to,
                endpoint_id,
                endpoint_id,
                status.value if status else None,
                status.value if status else None,
                severity,
                severity,
                rule_code,
                rule_code,
            ),
        ).fetchone()
        return int(row[0])

    def summary(
        self,
        *,
        from_: datetime,
        to: datetime,
        endpoint_id: int | None,
        interval_seconds: int,
    ) -> dict[str, Any]:
        filters = (from_, to, endpoint_id, endpoint_id)

        def grouped(columns: str, order_by: str = "event_count DESC", limit: int | None = None):
            pagination = " LIMIT %s" if limit is not None else ""
            values = filters if limit is None else filters + (limit,)
            with self.connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    f"""
                    SELECT {columns}, count(*) AS event_count
                    FROM alerts
                    WHERE is_delete = FALSE AND detected_at >= %s AND detected_at < %s
                      AND (%s::bigint IS NULL OR endpoint_id = %s::bigint)
                    GROUP BY {columns}
                    ORDER BY {order_by}{pagination}
                    """,
                    values,
                )
                return [dict(row) for row in cursor.fetchall()]

        total = self.connection.execute(
            """
            SELECT count(*) FROM alerts
            WHERE is_delete = FALSE AND detected_at >= %s AND detected_at < %s
              AND (%s::bigint IS NULL OR endpoint_id = %s::bigint)
            """,
            filters,
        ).fetchone()[0]
        time_rows = self.connection.execute(
            """
            SELECT date_bin(%s * interval '1 second', detected_at, TIMESTAMPTZ '1970-01-01 00:00:00+00'),
                   count(*)
            FROM alerts
            WHERE is_delete = FALSE AND detected_at >= %s AND detected_at < %s
              AND (%s::bigint IS NULL OR endpoint_id = %s::bigint)
            GROUP BY 1 ORDER BY 1
            """,
            (interval_seconds,) + filters,
        ).fetchall()
        active_rules = self.connection.execute(
            """
            SELECT rule_code, rule_version, severity, count(*)
            FROM alerts
            WHERE is_delete = FALSE AND detected_at >= %s AND detected_at < %s
              AND (%s::bigint IS NULL OR endpoint_id = %s::bigint)
              AND status IN ('OPEN', 'IN_PROGRESS')
            GROUP BY rule_code, rule_version, severity
            """,
            filters,
        ).fetchall()
        return {
            "total": int(total),
            "by_severity": {
                str(row["severity"]): int(row["event_count"])
                for row in grouped("severity", "severity ASC")
            },
            "by_status": {
                str(row["status"]): int(row["event_count"])
                for row in grouped("status", "status ASC")
            },
            "top_rules": grouped("rule_code, rule_name", "event_count DESC, rule_code ASC", 100),
            "mitre_tactics": grouped(
                "mitre_tactic_code, mitre_tactic_name",
                "event_count DESC, mitre_tactic_code ASC",
                100,
            ),
            "mitre_techniques": grouped(
                "mitre_technique_code, mitre_technique_name",
                "event_count DESC, mitre_technique_code ASC",
                100,
            ),
            "time_series": {row[0]: int(row[1]) for row in time_rows},
            "active_rules": [
                {
                    "rule_code": str(row[0]),
                    "rule_version": int(row[1]),
                    "severity": str(row[2]),
                    "count": int(row[3]),
                }
                for row in active_rules
            ],
        }

    def active_severity_count(self, *, endpoint_id: int | None, severity: str) -> int:
        row = self.connection.execute(
            """
            SELECT count(*) FROM alerts
            WHERE is_delete = FALSE AND status IN ('OPEN', 'IN_PROGRESS')
              AND severity = %s AND (%s::bigint IS NULL OR endpoint_id = %s::bigint)
            """,
            (severity, endpoint_id, endpoint_id),
        ).fetchone()
        return int(row[0])

    def detail(self, alert_id: int) -> dict[str, Any] | None:
        with self.connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute("SELECT * FROM alerts WHERE alert_id = %s AND is_delete = FALSE", (alert_id,))
            row = cursor.fetchone()
        return dict(row) if row is not None else None

    def incidents_for_alert(self, alert_id: int) -> list[dict[str, Any]]:
        with self.connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT i.incident_id, i.title, i.severity, i.status, i.window_start_at, i.window_end_at
                FROM incident_alerts ia JOIN incidents i ON i.incident_id = ia.incident_id
                WHERE ia.alert_id = %s AND ia.is_delete = FALSE AND i.is_delete = FALSE
                ORDER BY i.last_detected_at DESC, i.incident_id DESC
                """,
                (alert_id,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def active_for_endpoint(self, endpoint_id: int) -> list[dict[str, Any]]:
        with self.connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT alert_id, rule_code, rule_version, risk_score, detected_at, title
                FROM alerts
                WHERE endpoint_id = %s AND is_delete = FALSE AND status IN ('OPEN', 'IN_PROGRESS')
                """,
                (endpoint_id,),
            )
            return list(cursor.fetchall())


class IncidentRepository:
    def __init__(self, connection: Connection[Any]) -> None:
        self.connection = connection

    def upsert(self, incident: IncidentInsert) -> StoredIncident:
        now = incident.detected_at.astimezone(UTC)
        with self.connection.transaction():
            row = self.connection.execute(
                """
                INSERT INTO incidents (
                    endpoint_id, correlation_key, window_start_at, window_end_at, title, description,
                    severity, status, first_detected_at, last_detected_at, closed_at, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'OPEN', %s, %s, NULL, %s, %s)
                ON CONFLICT (endpoint_id, correlation_key, window_start_at) DO UPDATE SET
                    last_detected_at = GREATEST(incidents.last_detected_at, EXCLUDED.last_detected_at),
                    window_end_at = GREATEST(incidents.window_end_at, EXCLUDED.window_end_at),
                    severity = CASE
                        WHEN array_position(ARRAY['LOW','MEDIUM','HIGH','CRITICAL'], EXCLUDED.severity)
                           > array_position(ARRAY['LOW','MEDIUM','HIGH','CRITICAL'], incidents.severity)
                        THEN EXCLUDED.severity ELSE incidents.severity END,
                    updated_at = EXCLUDED.updated_at
                RETURNING incident_id, status, (xmax = 0) AS created
                """,
                (
                    incident.endpoint_id,
                    incident.correlation_key,
                    incident.window_start_at,
                    incident.window_end_at,
                    incident.title,
                    incident.description,
                    incident.severity.value,
                    now,
                    now,
                    now,
                    now,
                ),
            ).fetchone()
            if row is None:
                raise RuntimeError("incident upsert failed")
            return StoredIncident(int(row[0]), bool(row[2]), IncidentStatus(row[1]))

    def link_alert(self, *, incident_id: int, alert_id: int, linked_at: datetime) -> None:
        with self.connection.transaction():
            self.connection.execute(
                """
                INSERT INTO incident_alerts (incident_id, alert_id, linked_at, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (incident_id, alert_id) DO NOTHING
                """,
                (incident_id, alert_id, linked_at, linked_at, linked_at),
            )

    def close_expired(self, now: datetime) -> int:
        with self.connection.transaction():
            cursor = self.connection.execute(
                """
                UPDATE incidents
                SET status = 'CLOSED', closed_at = window_end_at, updated_at = %s
                WHERE is_delete = FALSE AND status = 'OPEN' AND window_end_at <= %s
                """,
                (now, now),
            )
            return int(cursor.rowcount)

    def open_for_endpoint(self, endpoint_id: int) -> list[dict[str, Any]]:
        with self.connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT incident_id, title, severity, last_detected_at
                FROM incidents
                WHERE endpoint_id = %s AND is_delete = FALSE AND status = 'OPEN'
                """,
                (endpoint_id,),
            )
            return list(cursor.fetchall())

    def list_rows(
        self,
        *,
        from_: datetime,
        to: datetime,
        endpoint_id: int | None = None,
        status: IncidentStatus | None = None,
        severity: str | None = None,
        sort_order: str = "desc",
        limit: int | None = None,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        direction = "ASC" if sort_order == "asc" else "DESC"
        pagination = " LIMIT %s OFFSET %s" if limit is not None else ""
        query = f"""
            SELECT i.*, count(ia.incident_alert_id) FILTER (WHERE ia.is_delete = FALSE) AS alert_count
            FROM incidents i
            LEFT JOIN incident_alerts ia ON ia.incident_id = i.incident_id
            WHERE i.is_delete = FALSE AND i.last_detected_at >= %s AND i.last_detected_at < %s
              AND (%s::bigint IS NULL OR i.endpoint_id = %s::bigint)
              AND (%s::text IS NULL OR i.status = %s::text)
              AND (%s::text IS NULL OR i.severity = %s::text)
            GROUP BY i.incident_id
            ORDER BY i.last_detected_at {direction}, i.incident_id {direction}{pagination}
        """
        values: tuple[Any, ...] = (
            from_,
            to,
            endpoint_id,
            endpoint_id,
            status.value if status else None,
            status.value if status else None,
            severity,
            severity,
        )
        if limit is not None:
            values += (limit, offset)
        with self.connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(query, values)
            return [dict(row) for row in cursor.fetchall()]

    def count_rows(
        self,
        *,
        from_: datetime,
        to: datetime,
        endpoint_id: int | None = None,
        status: IncidentStatus | None = None,
        severity: str | None = None,
    ) -> int:
        row = self.connection.execute(
            """
            SELECT count(*) FROM incidents i
            WHERE i.is_delete = FALSE AND i.last_detected_at >= %s AND i.last_detected_at < %s
              AND (%s::bigint IS NULL OR i.endpoint_id = %s::bigint)
              AND (%s::text IS NULL OR i.status = %s::text)
              AND (%s::text IS NULL OR i.severity = %s::text)
            """,
            (
                from_,
                to,
                endpoint_id,
                endpoint_id,
                status.value if status else None,
                status.value if status else None,
                severity,
                severity,
            ),
        ).fetchone()
        return int(row[0])

    def summary(
        self,
        *,
        from_: datetime,
        to: datetime,
        endpoint_id: int | None,
        interval_seconds: int,
    ) -> dict[str, Any]:
        filters = (from_, to, endpoint_id, endpoint_id)
        status_rows = self.connection.execute(
            """
            SELECT status, count(*) FROM incidents
            WHERE is_delete = FALSE AND last_detected_at >= %s AND last_detected_at < %s
              AND (%s::bigint IS NULL OR endpoint_id = %s::bigint)
            GROUP BY status
            """,
            filters,
        ).fetchall()
        severity_rows = self.connection.execute(
            """
            SELECT severity, count(*) FROM incidents
            WHERE is_delete = FALSE AND last_detected_at >= %s AND last_detected_at < %s
              AND (%s::bigint IS NULL OR endpoint_id = %s::bigint)
            GROUP BY severity
            """,
            filters,
        ).fetchall()
        time_rows = self.connection.execute(
            """
            SELECT date_bin(%s * interval '1 second', last_detected_at, TIMESTAMPTZ '1970-01-01 00:00:00+00'),
                   status, count(*)
            FROM incidents
            WHERE is_delete = FALSE AND last_detected_at >= %s AND last_detected_at < %s
              AND (%s::bigint IS NULL OR endpoint_id = %s::bigint)
            GROUP BY 1, status ORDER BY 1, status
            """,
            (interval_seconds,) + filters,
        ).fetchall()
        return {
            "by_status": {str(status): int(count) for status, count in status_rows},
            "by_severity": {str(severity): int(count) for severity, count in severity_rows},
            "time_series": [
                {"bucket_start_at": row[0], "status": str(row[1]), "count": int(row[2])}
                for row in time_rows
            ],
        }

    def detail(self, incident_id: int) -> dict[str, Any] | None:
        with self.connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT i.*, count(ia.incident_alert_id) FILTER (WHERE ia.is_delete = FALSE) AS alert_count
                FROM incidents i LEFT JOIN incident_alerts ia ON ia.incident_id = i.incident_id
                WHERE i.incident_id = %s AND i.is_delete = FALSE
                GROUP BY i.incident_id
                """,
                (incident_id,),
            )
            row = cursor.fetchone()
        return dict(row) if row is not None else None

    def alerts_for_incident(self, incident_id: int, *, limit: int | None = None) -> list[dict[str, Any]]:
        pagination = " LIMIT %s" if limit is not None else ""
        with self.connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                f"""
                SELECT a.* FROM incident_alerts ia JOIN alerts a ON a.alert_id = ia.alert_id
                WHERE ia.incident_id = %s AND ia.is_delete = FALSE AND a.is_delete = FALSE
                ORDER BY a.detected_at DESC, a.alert_id DESC{pagination}
                """,
                (incident_id,) if limit is None else (incident_id, limit),
            )
            return [dict(row) for row in cursor.fetchall()]

    def counts_by_event_ids(
        self,
        event_ids: Sequence[str],
        *,
        from_: datetime,
        to: datetime,
    ) -> dict[str, int]:
        if not event_ids:
            return {}
        rows = self.connection.execute(
            """
            SELECT event_id, count(*)
            FROM alerts
            WHERE is_delete = FALSE AND detected_at >= %s AND detected_at < %s
              AND event_id = ANY(%s::uuid[])
            GROUP BY event_id
            """,
            (from_, to, list(event_ids)),
        ).fetchall()
        return {str(event_id): int(count) for event_id, count in rows}


class IngestMetadataRepository:
    def __init__(self, connection: Connection[Any]) -> None:
        self.connection = connection

    def upsert(self, bucket: IngestBucket, now: datetime) -> None:
        with self.connection.transaction():
            self.connection.execute(
                """
                INSERT INTO ingest_metadata (
                    endpoint_id, bucket_start_at, bucket_end_at, storage_backend, storage_class,
                    storage_status, storage_path, event_count, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (endpoint_id, bucket_start_at, storage_backend, storage_class) DO UPDATE SET
                    bucket_end_at = EXCLUDED.bucket_end_at,
                    storage_status = EXCLUDED.storage_status,
                    storage_path = EXCLUDED.storage_path,
                    event_count = EXCLUDED.event_count,
                    updated_at = EXCLUDED.updated_at,
                    is_delete = FALSE
                """,
                (
                    bucket.endpoint_id,
                    bucket.bucket_start_at,
                    bucket.bucket_end_at,
                    bucket.storage_backend.value,
                    bucket.storage_class.value,
                    bucket.storage_status.value,
                    bucket.storage_path,
                    bucket.event_count,
                    now,
                    now,
                ),
            )

    @contextmanager
    def hot_ingest_guard(
        self,
        *,
        endpoint_id: int,
        occurred_at: datetime,
        now: datetime,
    ) -> Iterator[None]:
        bucket_start = occurred_at.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        bucket_end = bucket_start + timedelta(days=1)
        lock_name = f"edr_events:{bucket_start.date().isoformat()}"
        with self.connection.transaction():
            self.connection.execute("SELECT pg_advisory_xact_lock_shared(hashtext(%s))", (lock_name,))
            existing = self.connection.execute(
                """
                SELECT is_delete FROM ingest_metadata
                WHERE endpoint_id = %s AND bucket_start_at = %s
                  AND storage_backend = 'CLICKHOUSE' AND storage_class = 'HOT'
                FOR UPDATE
                """,
                (endpoint_id, bucket_start),
            ).fetchone()
            if existing is not None and bool(existing[0]):
                raise ArchivedDayImmutableError("Archived ClickHouse day cannot be recreated")
            if existing is None:
                self.connection.execute(
                    """
                    INSERT INTO ingest_metadata (
                        endpoint_id, bucket_start_at, bucket_end_at, storage_backend, storage_class,
                        storage_status, storage_path, event_count, created_at, updated_at
                    ) VALUES (%s, %s, %s, 'CLICKHOUSE', 'HOT', 'HOT', %s, 0, %s, %s)
                    """,
                    (
                        endpoint_id,
                        bucket_start,
                        bucket_end,
                        f"clickhouse://edr_events/date={bucket_start.date().isoformat()}/endpoint_id={endpoint_id}",
                        now,
                        now,
                    ),
                )
            self.connection.execute(
                """
                UPDATE ingest_metadata
                SET archive_verified_at = NULL, checksum_sha256 = NULL, updated_at = %s
                WHERE endpoint_id = %s AND bucket_start_at = %s
                  AND storage_backend = 'S3' AND storage_class = 'GLACIER_FLEXIBLE_RETRIEVAL'
                  AND archive_verified_at IS NOT NULL AND is_delete = FALSE
                """,
                (now, endpoint_id, bucket_start),
            )
            yield

    def overlapping(self, endpoint_ids: Sequence[int], from_: datetime, to: datetime) -> list[dict[str, Any]]:
        with self.connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT * FROM ingest_metadata
                WHERE endpoint_id = ANY(%s)
                  AND bucket_start_at < %s
                  AND bucket_end_at > %s
                  AND is_delete = FALSE
                ORDER BY bucket_start_at DESC, endpoint_id ASC
                """,
                (list(endpoint_ids), to, from_),
            )
            return list(cursor.fetchall())

    def overlapping_all(
        self,
        *,
        from_: datetime,
        to: datetime,
        endpoint_ids: Sequence[int] | None = None,
    ) -> list[dict[str, Any]]:
        with self.connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT * FROM ingest_metadata
                WHERE bucket_start_at < %s AND bucket_end_at > %s AND is_delete = FALSE
                  AND (%s::bigint[] IS NULL OR endpoint_id = ANY(%s::bigint[]))
                ORDER BY bucket_start_at DESC, endpoint_id ASC
                """,
                (
                    to,
                    from_,
                    list(endpoint_ids) if endpoint_ids is not None else None,
                    list(endpoint_ids) if endpoint_ids is not None else None,
                ),
            )
            return [dict(row) for row in cursor.fetchall()]

    def all_current(self) -> list[dict[str, Any]]:
        with self.connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute("SELECT * FROM ingest_metadata WHERE is_delete = FALSE")
            return [dict(row) for row in cursor.fetchall()]

    def summary(self, *, endpoint_id: int | None = None) -> dict[str, Any]:
        filters = (endpoint_id, endpoint_id)

        def grouped(column: str) -> dict[str, int]:
            rows = self.connection.execute(
                f"""
                SELECT {column}, count(*) FROM ingest_metadata
                WHERE is_delete = FALSE AND (%s::bigint IS NULL OR endpoint_id = %s::bigint)
                GROUP BY {column}
                """,
                filters,
            ).fetchall()
            return {str(value): int(count) for value, count in rows}

        total = self.connection.execute(
            """
            SELECT count(*) FROM ingest_metadata
            WHERE is_delete = FALSE AND (%s::bigint IS NULL OR endpoint_id = %s::bigint)
            """,
            filters,
        ).fetchone()[0]
        return {
            "total": int(total),
            "by_backend": grouped("storage_backend"),
            "by_class": grouped("storage_class"),
            "by_status": grouped("storage_status"),
        }

    def archive_candidates(self, *, completed_before: datetime, limit: int = 10) -> list[dict[str, Any]]:
        with self.connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT hot.*, archive.storage_path AS archive_storage_path
                FROM ingest_metadata AS hot
                LEFT JOIN ingest_metadata AS archive
                  ON archive.endpoint_id = hot.endpoint_id
                 AND archive.bucket_start_at = hot.bucket_start_at
                 AND archive.storage_backend = 'S3'
                 AND archive.storage_class = 'GLACIER_FLEXIBLE_RETRIEVAL'
                 AND archive.is_delete = FALSE
                WHERE hot.storage_backend = 'CLICKHOUSE'
                  AND hot.storage_class = 'HOT'
                  AND hot.storage_status = 'HOT'
                  AND hot.is_delete = FALSE
                  AND hot.bucket_end_at <= %s
                  AND (
                      archive.endpoint_id IS NULL
                      OR archive.archive_verified_at IS NULL
                      OR archive.checksum_sha256 IS NULL
                      OR archive.event_count <> hot.event_count
                  )
                ORDER BY hot.bucket_start_at ASC, hot.endpoint_id ASC
                LIMIT %s
                """,
                (completed_before, limit),
            )
            return [dict(row) for row in cursor.fetchall()]

    @contextmanager
    def archive_guard(self, *, endpoint_id: int, bucket_start_at: datetime) -> Iterator[dict[str, Any] | None]:
        lock_name = f"edr_events:{bucket_start_at.astimezone(UTC).date().isoformat()}"
        with self.connection.transaction():
            self.connection.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (lock_name,))
            with self.connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    """
                    SELECT * FROM ingest_metadata
                    WHERE endpoint_id = %s AND bucket_start_at = %s
                      AND storage_backend = 'CLICKHOUSE' AND storage_class = 'HOT'
                      AND storage_status = 'HOT' AND is_delete = FALSE
                    FOR UPDATE
                    """,
                    (endpoint_id, bucket_start_at),
                )
                row = cursor.fetchone()
            yield dict(row) if row is not None else None

    def record_verified_archive(
        self,
        *,
        endpoint_id: int,
        bucket_start_at: datetime,
        bucket_end_at: datetime,
        storage_path: str,
        event_count: int,
        size_bytes: int,
        checksum_sha256: str,
        verified_at: datetime,
    ) -> None:
        with self.connection.transaction():
            self.connection.execute(
                """
                UPDATE ingest_metadata
                SET event_count = %s, updated_at = %s
                WHERE endpoint_id = %s AND bucket_start_at = %s
                  AND storage_backend = 'CLICKHOUSE' AND storage_class = 'HOT'
                  AND storage_status = 'HOT' AND is_delete = FALSE
                """,
                (event_count, verified_at, endpoint_id, bucket_start_at),
            )
            self.connection.execute(
                """
                INSERT INTO ingest_metadata (
                    endpoint_id, bucket_start_at, bucket_end_at, storage_backend, storage_class,
                    storage_status, storage_path, event_count, size_bytes, checksum_sha256,
                    archived_at, archive_verified_at, restore_requested_at, restored_at,
                    restore_expires_at, last_error, created_at, updated_at, is_delete
                ) VALUES (
                    %s, %s, %s, 'S3', 'GLACIER_FLEXIBLE_RETRIEVAL', 'ARCHIVED', %s,
                    %s, %s, %s, %s, %s, NULL, NULL, NULL, NULL, %s, %s, FALSE
                )
                ON CONFLICT (endpoint_id, bucket_start_at, storage_backend, storage_class) DO UPDATE SET
                    bucket_end_at = EXCLUDED.bucket_end_at,
                    storage_status = 'ARCHIVED',
                    storage_path = EXCLUDED.storage_path,
                    event_count = EXCLUDED.event_count,
                    size_bytes = EXCLUDED.size_bytes,
                    checksum_sha256 = EXCLUDED.checksum_sha256,
                    archived_at = EXCLUDED.archived_at,
                    archive_verified_at = EXCLUDED.archive_verified_at,
                    restore_requested_at = NULL,
                    restored_at = NULL,
                    restore_expires_at = NULL,
                    last_error = NULL,
                    updated_at = EXCLUDED.updated_at,
                    is_delete = FALSE
                """,
                (
                    endpoint_id,
                    bucket_start_at,
                    bucket_end_at,
                    storage_path,
                    event_count,
                    size_bytes,
                    checksum_sha256,
                    verified_at,
                    verified_at,
                    verified_at,
                    verified_at,
                ),
            )

    def partition_deletion_candidates(self, *, verified_before: datetime, limit: int = 10) -> list[datetime]:
        rows = self.connection.execute(
            """
            SELECT bucket_start_at
            FROM ingest_metadata
            WHERE storage_backend = 'CLICKHOUSE' AND storage_class = 'HOT'
            GROUP BY bucket_start_at
            HAVING (
                bool_or(is_delete = TRUE AND partition_deleted_at IS NULL)
                OR (
                    bool_or(is_delete = FALSE)
                    AND bool_and(
                        is_delete = TRUE OR EXISTS (
                            SELECT 1 FROM ingest_metadata AS archive
                            WHERE archive.endpoint_id = ingest_metadata.endpoint_id
                              AND archive.bucket_start_at = ingest_metadata.bucket_start_at
                              AND archive.storage_backend = 'S3'
                              AND archive.storage_class = 'GLACIER_FLEXIBLE_RETRIEVAL'
                              AND archive.is_delete = FALSE
                              AND archive.archive_verified_at IS NOT NULL
                              AND archive.archive_verified_at <= %s
                              AND archive.checksum_sha256 IS NOT NULL
                              AND archive.event_count = ingest_metadata.event_count
                        )
                    )
                )
            )
            ORDER BY bucket_start_at ASC
            LIMIT %s
            """,
            (verified_before, limit),
        ).fetchall()
        return [row[0] for row in rows]

    def claim_partition_deletion(self, *, bucket_start_at: datetime, verified_before: datetime, now: datetime) -> bool:
        lock_name = f"edr_events:{bucket_start_at.astimezone(UTC).date().isoformat()}"
        with self.connection.transaction():
            self.connection.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (lock_name,))
            pending = self.connection.execute(
                """
                SELECT EXISTS (
                    SELECT 1 FROM ingest_metadata
                    WHERE bucket_start_at = %s AND storage_backend = 'CLICKHOUSE'
                      AND storage_class = 'HOT' AND is_delete = TRUE AND partition_deleted_at IS NULL
                )
                """,
                (bucket_start_at,),
            ).fetchone()[0]
            if pending:
                return True
            eligibility = self.connection.execute(
                """
                SELECT count(*) AS hot_count,
                       bool_and(EXISTS (
                           SELECT 1 FROM ingest_metadata AS archive
                           WHERE archive.endpoint_id = hot.endpoint_id
                             AND archive.bucket_start_at = hot.bucket_start_at
                             AND archive.storage_backend = 'S3'
                             AND archive.storage_class = 'GLACIER_FLEXIBLE_RETRIEVAL'
                             AND archive.is_delete = FALSE
                             AND archive.archive_verified_at IS NOT NULL
                             AND archive.archive_verified_at <= %s
                             AND archive.checksum_sha256 IS NOT NULL
                             AND archive.event_count = hot.event_count
                       )) AS all_verified
                FROM ingest_metadata AS hot
                WHERE hot.bucket_start_at = %s
                  AND hot.storage_backend = 'CLICKHOUSE' AND hot.storage_class = 'HOT'
                  AND hot.storage_status = 'HOT' AND hot.is_delete = FALSE
                """,
                (verified_before, bucket_start_at),
            ).fetchone()
            if int(eligibility[0]) == 0 or not bool(eligibility[1]):
                return False
            self.connection.execute(
                """
                UPDATE ingest_metadata
                SET is_delete = TRUE, updated_at = %s
                WHERE bucket_start_at = %s AND storage_backend = 'CLICKHOUSE'
                  AND storage_class = 'HOT' AND storage_status = 'HOT' AND is_delete = FALSE
                """,
                (now, bucket_start_at),
            )
            return True

    def mark_partition_deleted(self, *, bucket_start_at: datetime, deleted_at: datetime) -> None:
        with self.connection.transaction():
            self.connection.execute(
                """
                UPDATE ingest_metadata
                SET partition_deleted_at = %s, updated_at = %s
                WHERE bucket_start_at = %s AND storage_backend = 'CLICKHOUSE'
                  AND storage_class = 'HOT' AND is_delete = TRUE AND partition_deleted_at IS NULL
                """,
                (deleted_at, deleted_at, bucket_start_at),
            )

    def restore_buckets(
        self,
        endpoint_ids: Sequence[int],
        from_: datetime,
        to: datetime,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        pagination = " LIMIT %s OFFSET %s" if limit is not None else ""
        values: tuple[Any, ...] = (list(endpoint_ids), to, from_)
        if limit is not None:
            values += (limit, offset)
        with self.connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                f"""
                SELECT archive.*
                FROM ingest_metadata AS archive
                WHERE archive.endpoint_id = ANY(%s)
                  AND archive.bucket_start_at < %s
                  AND archive.bucket_end_at > %s
                  AND archive.storage_backend = 'S3'
                  AND archive.storage_class = 'GLACIER_FLEXIBLE_RETRIEVAL'
                  AND archive.is_delete = FALSE
                  AND NOT EXISTS (
                      SELECT 1
                      FROM ingest_metadata AS hot
                      WHERE hot.endpoint_id = archive.endpoint_id
                        AND hot.bucket_start_at = archive.bucket_start_at
                        AND hot.storage_backend = 'CLICKHOUSE'
                        AND hot.storage_class = 'HOT'
                        AND hot.storage_status = 'HOT'
                        AND hot.is_delete = FALSE
                  )
                ORDER BY archive.bucket_start_at DESC, archive.endpoint_id ASC{pagination}
                """,
                values,
            )
            return list(cursor.fetchall())

    def count_restore_buckets(self, endpoint_ids: Sequence[int], from_: datetime, to: datetime) -> int:
        row = self.connection.execute(
            """
            SELECT count(*)
            FROM ingest_metadata AS archive
            WHERE archive.endpoint_id = ANY(%s)
              AND archive.bucket_start_at < %s
              AND archive.bucket_end_at > %s
              AND archive.storage_backend = 'S3'
              AND archive.storage_class = 'GLACIER_FLEXIBLE_RETRIEVAL'
              AND archive.is_delete = FALSE
              AND NOT EXISTS (
                  SELECT 1 FROM ingest_metadata AS hot
                  WHERE hot.endpoint_id = archive.endpoint_id
                    AND hot.bucket_start_at = archive.bucket_start_at
                    AND hot.storage_backend = 'CLICKHOUSE'
                    AND hot.storage_class = 'HOT'
                    AND hot.storage_status = 'HOT'
                    AND hot.is_delete = FALSE
              )
            """,
            (list(endpoint_ids), to, from_),
        ).fetchone()
        return int(row[0])

    def restore_bucket(self, *, endpoint_id: int, bucket_start_at: datetime) -> dict[str, Any] | None:
        with self.connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT * FROM ingest_metadata
                WHERE endpoint_id = %s AND bucket_start_at = %s
                  AND storage_backend = 'S3' AND storage_class = 'GLACIER_FLEXIBLE_RETRIEVAL'
                  AND is_delete = FALSE
                """,
                (endpoint_id, bucket_start_at),
            )
            row = cursor.fetchone()
            return dict(row) if row is not None else None

    def requested_restores(self, *, limit: int = 100) -> list[dict[str, Any]]:
        with self.connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT * FROM ingest_metadata
                WHERE storage_backend = 'S3'
                  AND storage_class = 'GLACIER_FLEXIBLE_RETRIEVAL'
                  AND storage_status = 'RESTORE_REQUESTED'
                  AND is_delete = FALSE
                ORDER BY restore_requested_at ASC NULLS FIRST, endpoint_id ASC, bucket_start_at ASC
                LIMIT %s
                """,
                (limit,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def request_restore(
        self,
        *,
        endpoint_id: int,
        bucket_start_at: datetime,
        actor_identifier: str,
        request_id: str,
        requested_at: datetime,
    ) -> bool:
        with self.connection.transaction():
            row = self.connection.execute(
                """
                UPDATE ingest_metadata AS archive
                SET storage_status = 'RESTORE_REQUESTED',
                    restore_requested_at = %s,
                    restored_at = NULL,
                    restore_expires_at = NULL,
                    last_error = NULL,
                    updated_at = %s
                WHERE archive.endpoint_id = %s
                  AND archive.bucket_start_at = %s
                  AND archive.storage_backend = 'S3'
                  AND archive.storage_class = 'GLACIER_FLEXIBLE_RETRIEVAL'
                  AND archive.storage_status IN ('ARCHIVED', 'RESTORE_FAILED', 'EXPIRED')
                  AND archive.is_delete = FALSE
                  AND NOT EXISTS (
                      SELECT 1
                      FROM ingest_metadata AS hot
                      WHERE hot.endpoint_id = archive.endpoint_id
                        AND hot.bucket_start_at = archive.bucket_start_at
                        AND hot.storage_backend = 'CLICKHOUSE'
                        AND hot.storage_class = 'HOT'
                        AND hot.storage_status = 'HOT'
                        AND hot.is_delete = FALSE
                  )
                RETURNING archive.storage_status
                """,
                (requested_at, requested_at, endpoint_id, bucket_start_at),
            ).fetchone()
            if row is None:
                return False
            self.connection.execute(
                """
                INSERT INTO audit_logs (
                    actor_type, actor_identifier, action, resource_type, resource_id,
                    before_json, after_json, request_id, created_at
                ) VALUES (
                    'USER', %s, 'ARCHIVE_RESTORE_REQUESTED', 'INGEST_METADATA', %s,
                    NULL, jsonb_build_object('storageStatus', 'RESTORE_REQUESTED'), %s, %s
                )
                """,
                (actor_identifier, f"{endpoint_id}:{bucket_start_at.isoformat()}", request_id, requested_at),
            )
            return True

    def mark_restored(
        self,
        *,
        endpoint_id: int,
        bucket_start_at: datetime,
        restored_at: datetime,
        restore_expires_at: datetime,
    ) -> bool:
        with self.connection.transaction():
            cursor = self.connection.execute(
                """
                UPDATE ingest_metadata
                SET storage_status = 'RESTORED', restored_at = %s, restore_expires_at = %s,
                    last_error = NULL, updated_at = %s
                WHERE endpoint_id = %s AND bucket_start_at = %s
                  AND storage_backend = 'S3' AND storage_class = 'GLACIER_FLEXIBLE_RETRIEVAL'
                  AND storage_status = 'RESTORE_REQUESTED' AND is_delete = FALSE
                """,
                (restored_at, restore_expires_at, restored_at, endpoint_id, bucket_start_at),
            )
            return cursor.rowcount == 1

    def mark_restore_failed(
        self,
        *,
        endpoint_id: int,
        bucket_start_at: datetime,
        error: str,
        failed_at: datetime,
    ) -> bool:
        with self.connection.transaction():
            cursor = self.connection.execute(
                """
                UPDATE ingest_metadata
                SET storage_status = 'RESTORE_FAILED', last_error = %s, updated_at = %s
                WHERE endpoint_id = %s AND bucket_start_at = %s
                  AND storage_backend = 'S3' AND storage_class = 'GLACIER_FLEXIBLE_RETRIEVAL'
                  AND storage_status = 'RESTORE_REQUESTED' AND is_delete = FALSE
                """,
                (error, failed_at, endpoint_id, bucket_start_at),
            )
            return cursor.rowcount == 1

    def expire_restores(self, now: datetime) -> int:
        with self.connection.transaction():
            cursor = self.connection.execute(
                """
                UPDATE ingest_metadata
                SET storage_status = 'EXPIRED', updated_at = %s
                WHERE storage_backend = 'S3'
                  AND storage_class = 'GLACIER_FLEXIBLE_RETRIEVAL'
                  AND storage_status = 'RESTORED'
                  AND restore_expires_at <= %s
                  AND is_delete = FALSE
                """,
                (now, now),
            )
            return int(cursor.rowcount)
