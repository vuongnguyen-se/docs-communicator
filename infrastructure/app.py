#!/usr/bin/env python3
"""CDK entry point for CloudDocs AI.

The account comes from the active AWS CLI profile (CDK_DEFAULT_ACCOUNT); it is
never written to source. The Region is fixed by config (D-001).
"""

from __future__ import annotations

import os

import aws_cdk as cdk

from stacks.clouddocs_stack import CloudDocsStack
from stacks.config import load_config

app = cdk.App()
config = load_config(app)

CloudDocsStack(
    app,
    f"CloudDocsAI-{config.stage}",
    config=config,
    env=cdk.Environment(account=os.environ.get("CDK_DEFAULT_ACCOUNT"), region=config.region),
    description="CloudDocs AI: serverless RAG document assistant (ephemeral dev environment)",
)

# D-002: every resource is tagged so leftovers can be found after `cdk destroy`.
cdk.Tags.of(app).add("Project", "CloudDocsAI")
cdk.Tags.of(app).add("Stage", config.stage)

app.synth()
