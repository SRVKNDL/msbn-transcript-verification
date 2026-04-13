"""Compute construct: Lambda functions for the MSBN processing pipeline.

Seven Lambda functions (see architecture-plan.md Section 1):
  - IntakeLambda:          S3 event -> create application record, start workflow
  - ExtractLambda:         PDF -> page images -> Bedrock Nova -> extraction JSON
  - RuleEngineLambda:      Single-document rules (PHYS, CONT, PROG)
  - CrossDocLambda:        Cross-document rules (CROSS_001-003)
  - PopulationCheckLambda: Population-level rules (POP_001-003)
  - NotifyLambda:          SNS email to reviewer queue
  - DashboardApiLambda:    REST backend for reviewer dashboard

ExtractLambda uses a container image (poppler dependency).
All other Lambdas use standard zip deployment.
"""

from constructs import Construct


class ComputeConstruct(Construct):
    """Lambda functions for the MSBN transcript verification pipeline."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # TODO: Create IntakeLambda
        #   - Trigger: S3 event notification on raw/ prefix
        #   - Runtime: Python 3.11
        #   - Code: services/intake/

        # TODO: Create ExtractLambda
        #   - Runtime: Python 3.11 container image (needs poppler)
        #   - Code: services/extract/
        #   - Bedrock invoke permissions (Nova Lite, Nova Pro)
        #   - Timeout: 5 minutes (PDF rendering + Bedrock calls)

        # TODO: Create RuleEngineLambda
        #   - Runtime: Python 3.11
        #   - Code: services/rule_engine/

        # TODO: Create CrossDocLambda
        #   - Runtime: Python 3.11
        #   - Code: services/cross_doc/

        # TODO: Create PopulationCheckLambda
        #   - Runtime: Python 3.11
        #   - Code: services/population_check/

        # TODO: Create NotifyLambda
        #   - Runtime: Python 3.11
        #   - Code: services/notify/
        #   - SNS publish permissions

        # TODO: Create DashboardApiLambda
        #   - Runtime: Python 3.11
        #   - Code: services/dashboard_api/
        #   - Integrated with API Gateway
