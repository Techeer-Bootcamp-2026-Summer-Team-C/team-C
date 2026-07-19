from typing import Literal

from pydantic import Field

from .common import ContractModel, UtcDateTime
from .enums import DnsRecordType


class ForwardDnsQuery(ContractModel):
    domain: str = Field(description="정방향 조회할 Domain 이름입니다.", examples=["example.com"])


class ForwardDnsDto(ContractModel):
    domain: str
    ip_addresses: list[str]


class ReverseDnsQuery(ContractModel):
    ip: str = Field(description="역방향 조회할 IPv4 또는 IPv6 주소입니다.", examples=["8.8.8.8"])


class ReverseDnsDto(ContractModel):
    ip: str
    hostnames: list[str]


class DnsLookupQuery(ContractModel):
    query: str = Field(description="조회할 Domain 또는 IP 주소입니다.", examples=["example.com"])
    record_type: DnsRecordType = Field(description="조회할 DNS 레코드 유형입니다.", examples=["A"])


class DnsLookupDto(ContractModel):
    query: str
    record_type: DnsRecordType
    answers: list[str]


class RelatedValueDto(ContractModel):
    value: str
    value_type: Literal["IP", "DOMAIN"]
    sources: list[Literal["LIVE_DNS", "OBSERVED_EVENTS"]]


class CorrelationRelationshipDto(ContractModel):
    source_value: str
    source_type: Literal["IP", "DOMAIN"]
    target_value: str
    target_type: Literal["IP", "DOMAIN"]
    relation: Literal["RESOLVES_TO", "PTR_CANDIDATE", "SUBDOMAIN_OF"]
    sources: list[Literal["LIVE_DNS", "OBSERVED_EVENTS"]]


class CorrelationDto(ContractModel):
    input_value: str
    input_type: Literal["IP", "DOMAIN"]
    from_: UtcDateTime = Field(alias="from")
    to: UtcDateTime
    related: list[RelatedValueDto]
    relationships: list[CorrelationRelationshipDto]
