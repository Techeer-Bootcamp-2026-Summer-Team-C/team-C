from typing import Literal

from pydantic import Field

from .common import ContractModel, UtcDateTime
from .enums import DnsRecordType


class ForwardDnsQuery(ContractModel):
    domain: str


class ForwardDnsDto(ContractModel):
    domain: str
    ip_addresses: list[str]


class ReverseDnsQuery(ContractModel):
    ip: str


class ReverseDnsDto(ContractModel):
    ip: str
    hostnames: list[str]


class DnsLookupQuery(ContractModel):
    query: str
    record_type: DnsRecordType


class DnsLookupDto(ContractModel):
    query: str
    record_type: DnsRecordType
    answers: list[str]


class RelatedValueDto(ContractModel):
    value: str
    value_type: Literal["IP", "DOMAIN"]
    sources: list[Literal["LIVE_DNS", "OBSERVED_EVENTS"]]


class CorrelationDto(ContractModel):
    input_value: str
    input_type: Literal["IP", "DOMAIN"]
    from_: UtcDateTime = Field(alias="from")
    to: UtcDateTime
    related: list[RelatedValueDto]
