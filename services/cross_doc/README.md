# CrossDocLambda

Applies cross-document validation rules across all documents in a single application.

**Responsibilities:**
- Load extraction JSONs for every document in the application
- Apply CROSS_001: Fuzzy name match across documents (SP-1 identity verification)
- Apply CROSS_002: Institution consistency across transcript and diploma
- Apply CROSS_003: Date consistency across documents
- Write FLAG items to DynamoDB

**Runs after:** All ExtractLambda invocations complete (parallel Map state)
**Runtime:** Python 3.11
