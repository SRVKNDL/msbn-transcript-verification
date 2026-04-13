#!/usr/bin/env python3
"""CDK app entry point for the MSBN Transcript Verification stack."""

import aws_cdk as cdk

from stacks.msbn_transcript_stack import MsbnTranscriptStack

app = cdk.App()

env = cdk.Environment(region="us-east-1")

MsbnTranscriptStack(app, "MsbnTranscriptStack", env=env)

app.synth()
