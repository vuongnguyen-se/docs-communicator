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


def config_from_dict(raw: dict[str, Any]) -> Config:
    return Config(
        stage=str(raw.get("stage", "dev")),
        region=str(raw.get("region", "ap-southeast-1")),
        allowed_origins=[str(o) for o in raw.get("allowedOrigins", [])],
        throttle_rate_limit=float(raw.get("throttleRateLimit", 5)),
        throttle_burst_limit=int(raw.get("throttleBurstLimit", 10)),
    )


def load_config(scope: Construct) -> Config:
    raw = Node.of(scope).try_get_context("clouddocs") or {}
    return config_from_dict(raw)
