"""Typed access to the `clouddocs` CDK context block (see cdk.json).

Override at the command line, e.g. `cdk synth -c clouddocs='{...}'` is awkward,
so prefer editing cdk.json for non-secret settings. Never put secrets here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from constructs import Construct, Node


@dataclass(frozen=True)
class Config:
    stage: str
    region: str
    allowed_origins: list[str]
    throttle_rate_limit: float
    throttle_burst_limit: int
    generation_model: str  # inference profile id, e.g. apac.amazon.nova-lite-v1:0 (D-008)
    alarm_email: str | None = None  # deploy-time only (-c alarmEmail=...), never committed


def config_from_dict(raw: dict[str, Any]) -> Config:
    return Config(
        stage=str(raw.get("stage", "dev")),
        region=str(raw.get("region", "ap-southeast-1")),
        allowed_origins=[str(o) for o in raw.get("allowedOrigins", [])],
        throttle_rate_limit=float(raw.get("throttleRateLimit", 5)),
        throttle_burst_limit=int(raw.get("throttleBurstLimit", 10)),
        generation_model=str(raw.get("generationModel", "apac.amazon.nova-lite-v1:0")),
        alarm_email=str(raw["alarmEmail"]) if raw.get("alarmEmail") else None,
    )


def load_config(scope: Construct) -> Config:
    node = Node.of(scope)
    raw = dict(node.try_get_context("clouddocs") or {})
    email = node.try_get_context("alarmEmail")
    if email:
        raw["alarmEmail"] = str(email)
    return config_from_dict(raw)
