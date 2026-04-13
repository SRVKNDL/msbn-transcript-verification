"""Workflow construct: Step Functions Standard Workflow.

Pipeline states (see architecture-plan.md Section 1.2):
  1. Update Status: EXTRACTING
  2. Parallel Map: ExtractLambda per document
  3. Update Status: EVALUATING
  4. RuleEngineLambda (single-document rules)
  5. CrossDocLambda (cross-document rules)
  6. PopulationCheckLambda (population-level rules)
  7. Update Status: READY_FOR_REVIEW
  8. NotifyLambda (email reviewer queue)
  9. (Conditional) WaitForNursysReport on DENIED decisions

Standard Workflow chosen over Express for full execution history
retention, which is part of the audit trail (SP-9).
"""

from constructs import Construct


class WorkflowConstruct(Construct):
    """Step Functions state machine for the transcript processing pipeline."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # TODO: Define state machine with the pipeline states above.
        #   - Use Standard Workflow (not Express) for audit history.
        #   - Parallel Map state for document extraction.
        #   - Error handling and retry on transient Bedrock failures.
        #   - Execution history retained for audit (SP-9).
