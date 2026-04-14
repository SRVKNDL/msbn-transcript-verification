"""Workflow construct: Step Functions Standard Workflow for the transcript pipeline.

Pipeline states (this slice — skeleton only):
  1. Extract      — invoke ExtractLambda
  2. Aggregate    — invoke AggregationLambda (cross-document field comparison)
  3. Validate     — invoke ValidateLambda (RuleEngine)
  4. QueueForReview — invoke QueueForReviewLambda (Notify)

Full pipeline from architecture-plan.md Section 1.2 will expand these states
in subsequent slices (Parallel Map for extraction, CrossDoc, PopulationCheck,
NotifyLambda, WaitForNursysReport).

Error handling:
  - Each Lambda Invoke state retries on transient Lambda service errors
    (Lambda.ServiceException, Lambda.AWSLambdaException, Lambda.SdkClientException):
    2 retries, exponential backoff (backoff_rate=2, interval=1s).
  - Any unhandled failure (after retries) is caught by the global catch:
    writes FAILED status to DynamoDB, then transitions to a Fail end state.

Workflow type: Standard (not Express) — full execution history retained for
SP-9 audit trail (architecture-plan.md Section 2.1).
"""

from aws_cdk import (
    Duration,
    aws_dynamodb as dynamodb,
    aws_lambda as lambda_,
    aws_logs as logs,
    aws_stepfunctions as sfn,
    aws_stepfunctions_tasks as sfn_tasks,
)
from constructs import Construct


# Lambda service errors that warrant a retry (transient infrastructure faults).
# Business-logic errors (raised by the Lambda handler itself) are NOT listed here
# so they propagate immediately to the catch block for human review.
_LAMBDA_TRANSIENT_ERRORS = [
    "Lambda.ServiceException",
    "Lambda.AWSLambdaException",
    "Lambda.SdkClientException",
]


class WorkflowConstruct(Construct):
    """Step Functions state machine for the MSBN transcript verification pipeline."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        extract_lambda: lambda_.IFunction,
        aggregate_lambda: lambda_.IFunction,
        validate_lambda: lambda_.IFunction,
        queue_for_review_lambda: lambda_.IFunction,
        table: dynamodb.ITable,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ── CloudWatch log group ───────────────────────────────────────────────
        # Hub Guide: 7-day retention for all Lambda and Step Functions logs.
        log_group = logs.LogGroup(
            self,
            "StateMachineLogGroup",
            retention=logs.RetentionDays.ONE_WEEK,
        )

        # ── Failure end states ─────────────────────────────────────────────────
        # WriteFailedStatus updates the DynamoDB METADATA item to status=FAILED
        # so the dashboard can surface failed applications.  The catch result
        # (error + cause) is placed at $.error; the original input fields
        # (applicationId, pk, etc.) remain accessible at the top level.
        write_failed = sfn_tasks.DynamoUpdateItem(
            self,
            "WriteFailedStatus",
            table=table,
            key={
                # $.pk is "APP#{applicationId}", passed in the execution input
                # by the Intake Lambda so we avoid a States.Format intrinsic here.
                "PK": sfn_tasks.DynamoAttributeValue.from_string(
                    sfn.JsonPath.string_at("$.pk")
                ),
                "SK": sfn_tasks.DynamoAttributeValue.from_string("METADATA"),
            },
            update_expression="SET #st = :failed",
            expression_attribute_names={"#st": "status"},
            expression_attribute_values={
                ":failed": sfn_tasks.DynamoAttributeValue.from_string("FAILED"),
            },
            result_path=sfn.JsonPath.DISCARD,
            comment="Write FAILED status to DynamoDB so the dashboard surfaces the error",
        )

        pipeline_failed = sfn.Fail(
            self,
            "PipelineFailed",
            error="PipelineError",
            cause="One or more pipeline states failed after retries; see execution history",
        )

        # Failure chain: write status → terminal Fail state.
        write_failed.next(pipeline_failed)

        # ── Pipeline states ────────────────────────────────────────────────────

        extract_task = self._lambda_task(
            "Extract",
            extract_lambda,
            write_failed,
            comment="Invoke ExtractLambda: PDF → page images → Bedrock extraction JSON",
        )

        aggregate_task = self._lambda_task(
            "Aggregate",
            aggregate_lambda,
            write_failed,
            comment="Invoke AggregationLambda: compare CROSS_* fields across all extraction JSONs",
        )

        validate_task = self._lambda_task(
            "Validate",
            validate_lambda,
            write_failed,
            comment="Invoke ValidateLambda: apply PHYS/CONT/PROG rules against extraction JSON",
        )

        queue_task = self._lambda_task(
            "QueueForReview",
            queue_for_review_lambda,
            write_failed,
            comment="Invoke QueueForReviewLambda: notify reviewer queue via SNS",
        )

        # ── State machine ──────────────────────────────────────────────────────
        self.state_machine = sfn.StateMachine(
            self,
            "TranscriptPipeline",
            state_machine_name="msbn-transcript-pipeline",
            # Standard Workflow: persists full execution history for SP-9 audit trail.
            state_machine_type=sfn.StateMachineType.STANDARD,
            definition_body=sfn.DefinitionBody.from_chainable(
                extract_task.next(aggregate_task).next(validate_task).next(queue_task)
            ),
            logs=sfn.LogOptions(
                destination=log_group,
                level=sfn.LogLevel.ALL,
                include_execution_data=True,
            ),
        )

    # ── Helper ─────────────────────────────────────────────────────────────────

    def _lambda_task(
        self,
        state_name: str,
        fn: lambda_.IFunction,
        failure_handler: sfn.IChainable,
        *,
        comment: str = "",
    ) -> sfn_tasks.LambdaInvoke:
        """Return a LambdaInvoke task with standard retry and catch configuration.

        - Passes the entire state input to the Lambda as its event payload.
        - Discards the Lambda response (ResultPath: null) so the original input
          fields (applicationId, pk, etc.) flow unchanged to the next state.
        - Retries twice on transient Lambda infrastructure errors with
          exponential backoff before routing to the failure handler.
        - Any other error (including Lambda handler exceptions) is caught
          immediately and routed to the failure handler.
        """
        task = sfn_tasks.LambdaInvoke(
            self,
            state_name,
            lambda_function=fn,
            # Pass the full state input as the Lambda event payload.
            payload=sfn.TaskInput.from_json_path_at("$"),
            # Discard task output; propagate original input to the next state.
            result_path=sfn.JsonPath.DISCARD,
            comment=comment,
        )

        # Retry on transient Lambda infrastructure errors only.
        # Business errors (raised by handler code) are NOT retried.
        task.add_retry(
            errors=_LAMBDA_TRANSIENT_ERRORS,
            max_attempts=2,
            backoff_rate=2,
            interval=Duration.seconds(1),
        )

        # Catch all errors after retries are exhausted and route to the failure
        # handler.  The error details are placed at $.error so the failure
        # handler can log them without overwriting the pipeline input.
        task.add_catch(
            failure_handler,
            errors=["States.ALL"],
            result_path="$.error",
        )

        return task
