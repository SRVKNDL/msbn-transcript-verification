"""Step Functions workflow for transcript processing."""

from aws_cdk import (
    Duration,
    aws_dynamodb as dynamodb,
    aws_lambda as lambda_,
    aws_logs as logs,
    aws_stepfunctions as sfn,
    aws_stepfunctions_tasks as sfn_tasks,
)
from constructs import Construct


# Retry only Lambda service faults. Handler errors should fail fast into the
# FAILED status path so reviewers can see the broken application.
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

        # Keep workflow logs short-lived for the POC budget.
        log_group = logs.LogGroup(
            self,
            "StateMachineLogGroup",
            retention=logs.RetentionDays.ONE_WEEK,
        )

        # Mark the application FAILED before ending the workflow.
        write_failed = sfn_tasks.DynamoUpdateItem(
            self,
            "WriteFailedStatus",
            table=table,
            key={
                # Intake passes the PK so this state stays simple.
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

        # Failure path: update metadata, then end in Fail.
        write_failed.next(pipeline_failed)

        # Extract consumes the full Intake payload and stores its result for Aggregate.
        extract_task = self._lambda_task(
            "Extract",
            extract_lambda,
            write_failed,
            result_path="$.extract_result",
            comment="Invoke ExtractLambda: PDF → page images → Bedrock extraction JSON",
        )

        # Aggregate only needs the extraction JSON key.
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

        # Validate runs the rules and exposes flag_count for QueueForReview.
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

        # QueueForReview is terminal; discard its output.
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

        self.state_machine = sfn.StateMachine(
            self,
            "TranscriptPipeline",
            state_machine_name="msbn-transcript-pipeline",
            # Standard keeps execution history for the audit requirement.
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
        """Create a Lambda task with the pipeline retry/catch defaults."""
        task = sfn_tasks.LambdaInvoke(
            self,
            state_name,
            lambda_function=fn,
            # Omitting payload forwards the full state input.
            payload=payload,
            # Merge the Lambda return dict, not the Invoke API envelope.
            payload_response_only=True,
            result_path=result_path if result_path is not None else sfn.JsonPath.DISCARD,
            comment=comment,
        )

        # Retry platform faults only; handler exceptions go to the catch path.
        task.add_retry(
            errors=_LAMBDA_TRANSIENT_ERRORS,
            max_attempts=2,
            backoff_rate=2,
            interval=Duration.seconds(1),
        )

        # Keep error details at $.error without replacing the original input.
        task.add_catch(
            failure_handler,
            errors=["States.ALL"],
            result_path="$.error",
        )

        return task
