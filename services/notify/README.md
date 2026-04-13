# NotifyLambda

Sends email notifications to the reviewer queue when an application is ready for review.

**Responsibilities:**
- Receive application ID and flag summary from Step Functions
- Publish a notification to the reviewer SNS topic
- Include application ID, flag count, and high-severity flag count in the message

**Trigger:** Step Functions state after all rules complete and status is `READY_FOR_REVIEW`
**Runtime:** Python 3.11
