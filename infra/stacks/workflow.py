"""Workflow construct: Step Functions Standard Workflow for the transcript pipeline.

Pipeline states (this slice — skeleton only):
  1. Extract        — invoke ExtractLambda
  2. Aggregate      — invoke AggregationLambda (cross-document field comparison)
  3. Validate       — invoke ValidateLambda (RuleEngine)
  4. QueueForReview — invoke QueueForReviewLambda (Notify)

Full pipeline from architecture-plan.md Section 1.2 will expand these states
in subsequent slices (Parallel Map for extraction, CrossDoc, PopulationCheck,
NotifyLambda, WaitForNursysReport).

Inter-state data flow
---------------------
Each Lambda's result is merged into the state under a dedicated key so
downstream states can read the values they need without clobbering the
original Intake input (``applicationId``, ``bucket``, ``s3_key``, ``pk``):

    Extract        → result_path="$.extract_result"
    Aggregate      → result_path="$.aggregate_result"
    Validate       → result_path="$.validate_result"
    QueueForReview → End (no downstream consumer)

Each downstream Lambda is invoked with an input shaped via ``TaskInput`` so
the event the handler receives is a small, explicit dict — not the entire
accumulated state. This keeps handler contracts stable as the pipeline grows.

Error handling
--------------
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

        # Extract consumes the full Intake input (applicationId, bucket, s3_key).
        # Its result (applicationId, page_count, extraction_s3_key) is merged
        # into the state at $.extract_result so Aggregate can read the key.
        extract_task = self._lambda_task(
            "Extract",
            extract_lambda,
            write_failed,
            result_path="$.extract_result",
            comment="Invoke ExtractLambda: PDF → page images → Bedrock extraction JSON",
        )

        # Aggregate reads the extraction JSON key from the merged state
        # (placed there by the Extract state). Its own result (applicationId,
        # aggregation_s3_key) is merged at $.aggregate_result.
        aggregate_task = self._lambda_task(
            "Aggregate",
            aggregate_lambda,
            write_failed,
            payload=sfn.TaskInput.from_object({
                "applicationId": sfn.JsonPath.string_at("$.applicationId"),
                "extraction_s3_key": sfn.JsonPath.string_at(
                    "$.extract_result.extraction_s3_key"
                ),
            }),
            result_path="$.aggregate_result",
            comment="Invoke AggregationLambda: flatten per-page extraction to aggregation.json",
        )

        # Validate reads the aggregation.json key Aggregate produced, runs the
        # rule engine, and merges its summary (flag_count, flags) at
        # $.validate_result so QueueForReview can read flag_count.
        validate_task = self._lambda_task(
            "Validate",
            validate_lambda,
            write_failed,
            payload=sfn.TaskInput.from_object({
                "applicationId": sfn.JsonPath.string_at("$.applicationId"),
                "aggregation_s3_key": sfn.JsonPath.string_at(
                    "$.aggregate_result.aggregation_s3_key"
                ),
            }),
            result_path="$.validate_result",
            comment="Invoke ValidateLambda: apply PHYS/CONT/PROG rules against aggregation.json",
        )

        # QueueForReview is the terminal state: no downstream reader, so its
        # output is discarded. It still needs flag_count, which Validate placed
        # at $.validate_result.flag_count.
        queue_task = self._lambda_task(
            "QueueForReview",
            queue_for_review_lambda,
            write_failed,
            payload=sfn.TaskInput.from_object({
                "applicationId": sfn.JsonPath.string_at("$.applicationId"),
                "flag_count": sfn.JsonPath.number_at(
                    "$.validate_result.flag_count"
                ),
            }),
            result_path=sfn.JsonPath.DISCARD,
            comment="Invoke QueueForReviewLambda: mark READY_FOR_REVIEW, write audit",
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
        payload: sfn.TaskInput | None = None,
        result_path: str | None = None,
        comment: str = "",
    ) -> sfn_tasks.LambdaInvoke:
        """Return a LambdaInvoke task with standard retry and catch configuration.

        ``payload`` defaults to the entire state input (``$``). Pass a
        ``TaskInput.from_object({...})`` to shape a specific event dict for the
        Lambda — preferred over ``$`` when the handler only needs a subset of
        fields.

        ``result_path`` defaults to DISCARD. Pass ``"$.<key>"`` to merge the
        Lambda's result into the state under that key so later states can read
        it.

        Retries on transient Lambda infrastructure errors only; business errors
        propagate immediately to the failure handler.
        """
        task = sfn_tasks.LambdaInvoke(
            self,
            state_name,
            lambda_function=fn,
            # Omit payload entirely to forward the full state input. Passing
            # from_json_path_at("$") here serializes the literal string "$".
            payload=payload,
            # payload_response_only: merge only the Lambda's return dict into
            # state, not the {StatusCode, Payload} envelope. This is what makes
            # $.extract_result.extraction_s3_key resolve at the next state.
            payload_response_only=True,
            result_path=result_path if result_path is not None else sfn.JsonPath.DISCARD,
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
