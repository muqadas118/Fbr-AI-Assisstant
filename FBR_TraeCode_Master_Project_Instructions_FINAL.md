# FBR AI Tax & Compliance SaaS
# TRAECODE MASTER PROJECT INSTRUCTIONS
# FINAL / LOCKED PROJECT DIRECTIVE

## 0. ROLE

You are working on an existing FBR AI Tax & Compliance SaaS project.

This is NOT a greenfield project and NOT a throwaway MVP.

The goal is to continue the existing project from its real current state and eventually deliver a production-oriented, launchable product for FBR/tax and compliance use cases.

You are responsible for:
- understanding the existing repository before changing it
- preserving valid existing work
- continuing from the current verified state
- implementing only what is actually required
- maintaining correctness, traceability, security, privacy, reliability, and testability
- avoiding unnecessary complexity and overengineering

Do not assume that a blank project should be created.

---

# 1. ABSOLUTE RULE: CONTINUE THE EXISTING PROJECT

## DO NOT rebuild the project from scratch.

The existing repository is the primary source of truth.

You MUST first inspect and audit what already exists.

You MUST preserve valid existing:
- code
- data
- scripts
- configuration
- validation logic
- directory structure
- documentation
- tests
- generated outputs
- source provenance
- progress tracking

Do NOT:
- delete the existing project
- reset the repository
- recreate completed phases unnecessarily
- replace working scripts merely because you prefer another implementation
- regenerate the entire dataset without a demonstrated need
- move files around without a concrete reason
- introduce a new architecture just because it is fashionable
- create duplicate versions of existing functionality

If something is already correct, keep it.

If something is broken, determine exactly why before changing it.

---

# 2. CURRENT PROJECT CONTINUATION POINT

The project has already gone through substantial data preparation and source-processing work.

The current continuation point is the DAILY UPDATE / SOURCE CHANGE DETECTION layer and the work immediately after it.

Therefore:

**DO NOT go backwards and restart from data cleaning.**

**DO NOT restart the entire source-document processing phase.**

**DO NOT recreate already completed datasets.**

Instead:

1. audit all previous work
2. verify the current state
3. identify the last genuinely verified completed stage
4. inspect the daily-update implementation and its test
5. preserve valid work
6. fix only blockers that genuinely prevent continuation
7. continue forward from the current verified state

If the audit finds an earlier issue, do NOT automatically rebuild the earlier stage. Determine whether:
- it is harmless,
- it is already handled,
- it is a documentation issue,
- it is a validation issue,
- or it genuinely blocks the next stage.

Only fix what is necessary.

---

# 3. MANDATORY FIRST ACTION: FULL PROJECT AUDIT

Before writing or changing implementation code, perform a complete repository audit.

The first task is AUDIT, not implementation.

Inspect at minimum:

- full directory tree
- README/documentation
- PROGRESS.md
- all scripts
- data directories
- raw source documents
- extracted source documents
- normalized data if present
- validation scripts
- test scripts
- configuration files
- dependency files
- logs/state files
- existing APIs/services if any
- frontend if any
- database/vector-store components if any
- environment/configuration handling
- security-sensitive configuration
- git status/history if available

Do not merely list files.

Understand what each important component does.

---

# 4. AUDIT OUTPUT

After the audit, produce a concise but technically complete current-state report.

Classify important components as:

- COMPLETED
- VERIFIED
- PARTIALLY COMPLETED
- NEEDS FIX
- FAILED
- MISSING
- UNKNOWN / NEEDS VERIFICATION

For each important phase, state:

1. What exists
2. What has been verified
3. What has not been verified
4. Any known failure
5. Whether it blocks continuation
6. The exact next action

Do NOT start implementing until the audit establishes a reliable current state.

If the repository's existing documentation conflicts with actual code/data, trust the actual repository state after verification and update PROGRESS.md accordingly.

---

# 5. KNOWN CURRENT DAILY-UPDATE TEST CONTEXT

The existing project has a daily update mechanism.

The intended behavior is:

1. Discover official FBR source documents.
2. Detect new or changed documents.
3. Trigger only the required downstream processing.
4. Run extraction/validation as required.
5. Do not advance the source hash/state if processing fails.
6. Preserve the original source on failure.
7. Continue safely once the failure is fixed.

A test was already performed using a temporary modification of:

`data/profile/source_docs/raw/20266291261044366FinanceAct2026.pdf`

The test temporarily changed the file hash.

Observed behavior:
- hash changed successfully
- daily_update.py detected exactly one changed document
- extraction was triggered
- extraction validation ran
- validation failed because of existing extraction issues
- daily update stopped
- source hash state was NOT advanced
- original file was restored exactly
- temporary backup was removed

This means the change-detection test demonstrated useful behavior, but it did NOT prove that the entire downstream pipeline is complete.

You MUST distinguish:
- change detection working
from
- extraction/validation being fully healthy.

Do not misrepresent the test result.

---

# 6. CURRENT KNOWN DATA/EXTRACTION CONTEXT

The existing extraction audit has previously processed 94 source documents.

A prior run showed:
- 84 successfully extracted
- 4 manual-review-required
- 6 failed extraction

Known problematic files included Finance Act 2025/2026 and several property valuation PDFs, with PDF stream/EOF errors.

A later validation run showed:
- expected extractable docs: 90
- JSON files found: 93
- valid extracted files: 90
- missing extracted file: PropertyValuation\PropertyValuation_Vehari.json
- invalid extracted files:
  - CPR_ComputerizedPaymentReceipt.json
  - CPR_Format_BulkData.json
  - TaxDepositForm.json

The three invalid JSON files were associated with documents requiring manual review and had missing expected fields.

IMPORTANT:
Do not assume these are the only current issues.

The audit MUST inspect the actual repository and rerun appropriate validation before deciding the current state.

Do not delete problematic source documents merely to make validation pass.

Do not hide failed documents.

Do not fake JSON output.

If a document genuinely requires manual review, preserve that status and make the pipeline handle it explicitly and safely.

---

# 7. LOCKED DEVELOPMENT WORKFLOW

The project workflow is:

1. DATA CLEANING
2. SOURCE DOCUMENT PROCESSING
3. NORMALIZATION
4. CHUNKING
5. EMBEDDINGS
6. VECTOR DATABASE
7. RAG
8. VERIFICATION LAYER
9. ROUTER / SPECIALIZED AGENTS
10. BACKEND API
11. FRONTEND
12. AUTH / USERS / ORGANIZATIONS
13. FINAL TESTING / DEPLOYMENT

This order is LOCKED.

Do not skip ahead because a later component looks more interesting.

Do not implement:
- embeddings
- vector database
- RAG
- agents
- LangChain/LangGraph
- FastAPI
- frontend
- authentication
- SaaS organization architecture

until the preceding stages are genuinely ready.

Exception:
You may inspect future-stage requirements during planning so that earlier interfaces are designed sensibly, but do not prematurely implement future-stage systems.

---

# 8. WORKFLOW IMAGE IS AUTHORITATIVE

If the project owner provides a workflow/architecture image:

- inspect it carefully
- treat it as authoritative for the intended workflow
- follow its order and relationships
- do not replace it with a different architecture
- do not invent additional layers without justification
- do not remove required layers
- do not reinterpret it into an unrelated architecture

If the image and existing code appear inconsistent:
1. report the inconsistency
2. explain it
3. preserve existing valid work
4. ask for clarification only if the conflict materially affects implementation

Do not silently redesign the project.

---

# 9. PRODUCTION-ORIENTED, NOT MVP

This is NOT an MVP-only assignment.

The final system is intended to become a proper product.

Therefore, throughout development, consider:

- correctness
- reliability
- maintainability
- scalability where justified
- privacy
- security
- tenant isolation
- authentication/authorization
- auditability
- logging
- error handling
- observability
- testing
- data provenance
- source traceability
- reproducibility
- safe updates
- rollback/recovery
- rate limiting where appropriate
- secure secrets management
- API validation
- input validation
- abuse prevention
- deployment configuration
- backups/recovery
- legal/tax-data traceability

However:

**PRODUCTION-ORIENTED DOES NOT MEAN OVERENGINEERED.**

Implement production requirements at the appropriate complexity level.

Do not build microservices merely because they are considered "production".

Do not add Kubernetes, event buses, message queues, distributed systems, multiple databases, elaborate agent frameworks, or complex orchestration unless there is a demonstrated requirement.

Prefer a simple architecture that can reliably satisfy the actual requirements.

---

# 10. NO OVERENGINEERING

Use this rule:

> The simplest design that correctly satisfies the requirement is preferred.

Before adding a dependency, framework, service, abstraction, or layer, ask:

1. Is it required?
2. Does the current project already solve this?
3. Does it materially improve correctness/reliability/security?
4. Will it create unnecessary maintenance?
5. Can the same requirement be met with the existing stack?

If the answer is no, do not add it.

Do not create files simply to make the project look more sophisticated.

---

# 11. CODE QUALITY RULES

All new code must be:

- readable
- modular
- testable
- deterministic where possible
- documented where necessary
- appropriately typed
- explicit about errors
- safe with paths and files
- safe with external input
- compatible with the existing project structure

Avoid:
- giant files
- giant functions
- duplicate utilities
- unnecessary abstractions
- hidden global state
- magic constants where configuration is appropriate
- silent exception swallowing
- fake success statuses
- hardcoded secrets
- dead code
- unnecessary dependencies

Do not rewrite good existing code for style alone.

---

# 12. DATA INTEGRITY RULES

Tax and compliance data is high-value data.

Never:
- silently alter source documents
- overwrite official source material unnecessarily
- fabricate missing values
- invent legal/tax rules
- modify tax rates without source evidence
- merge conflicting versions without preserving provenance
- delete failed documents just to pass validation

Maintain:
- original source
- source identity
- source URL where available
- retrieval metadata
- document version/date where available
- extraction status
- validation status
- transformation history

Derived data must remain traceable back to the source.

---

# 13. FBR SOURCE RULE

Official FBR sources should be prioritized for tax/legal source material.

When the system processes official documents:

- preserve official document identity
- preserve source URL
- preserve retrieval timestamp where appropriate
- detect updates reliably
- avoid duplicate downloads
- detect actual content changes using robust hashing
- do not assume a filename change is the only form of change

The source-update mechanism must fail safely.

---

# 14. DAILY UPDATE REQUIREMENTS

The daily update layer should eventually support:

### Discovery
Find relevant official FBR source documents.

### Deduplication
Avoid unnecessary duplicate downloads.

### Change detection
Use content-based hashing or equivalent robust comparison.

### Processing
Only process documents that are new or actually changed.

### Validation
Run appropriate validation after processing.

### Failure safety
If downstream processing fails:
- do not mark the source as successfully processed
- do not advance the hash/state
- preserve the original source
- expose the failure clearly

### Recovery
After the issue is fixed, rerunning the update should safely process the outstanding source.

### Idempotency
Running daily_update.py twice without source changes should not rebuild everything.

---

# 15. VALIDATION IS MANDATORY

Never declare a stage complete simply because a script exited without crashing.

A stage is complete only when appropriate validation proves it.

Use:

- structural validation
- schema validation
- semantic validation
- regression tests
- integrity checks
- failure-path tests where relevant

If validation fails, report exactly why.

Do not weaken validation just to obtain PASS.

Do not modify validation rules merely to hide an implementation defect.

---

# 16. TESTING RULES

Every meaningful subsystem should have tests appropriate to its role.

Tests should include where applicable:

- happy path
- empty input
- malformed input
- duplicate input
- changed source
- unchanged source
- missing source
- failed download
- failed extraction
- invalid extraction
- recovery after failure
- idempotent rerun
- security-sensitive input
- authorization boundaries
- tenant isolation
- API validation
- RAG grounding
- citation/provenance

Test utilities must not permanently damage production/source data.

Temporary test modifications must:
- create backups safely
- restore data exactly
- clean up temporary files
- verify restoration

---

# 17. AI / TAX ANSWER SAFETY

The eventual assistant must not confidently invent tax/legal answers.

The system should be designed so that answers are:

- grounded in approved sources
- traceable to source material
- explicit about uncertainty
- version-aware
- date-aware
- resistant to unsupported claims

Where appropriate, responses should provide source/citation information.

The assistant should distinguish between:
- source-backed fact
- calculation
- interpretation
- uncertainty

If the system cannot establish sufficient evidence, it should not fabricate an answer.

---

# 18. RAG REQUIREMENTS FOR LATER STAGES

When the project reaches RAG:

- retrieval quality matters more than flashy framework usage
- chunks must preserve context
- metadata must be meaningful
- source provenance must survive retrieval
- version/date information must be retained
- conflicting source versions must be handled deliberately
- generated answers must be grounded in retrieved evidence
- unsupported claims should be detectable
- verification must be separate from generation

Do not implement RAG before the source data pipeline is ready.

---

# 19. VERIFICATION LAYER

The verification layer must not be a cosmetic wrapper around the LLM.

It should eventually help verify:

- whether claims are supported by retrieved evidence
- whether calculations are internally consistent
- whether required source evidence exists
- whether the source/version is appropriate
- whether the answer contains unsupported claims
- whether a response should be rejected or qualified

Design it according to actual requirements rather than inventing an unnecessarily complex multi-agent verification system.

---

# 20. PRIVACY AND SECURITY

Because the eventual product may process sensitive tax/business/user information, security must be treated as a core product requirement.

Later stages must consider:

- secure authentication
- authorization
- least privilege
- tenant isolation
- secure password handling where applicable
- session/token security
- secure secrets management
- encryption in transit
- appropriate encryption at rest
- input validation
- output safety
- secure file handling
- logging without leaking sensitive information
- audit trails
- retention/deletion policies
- backup security
- rate limiting
- abuse protection
- secure dependency management

Never put secrets/API keys/passwords in source code.

Never commit real credentials.

Never expose sensitive user information in logs unnecessarily.

---

# 21. MULTI-TENANT PRODUCT REQUIREMENT

The final product is intended to support organizations/users.

Therefore, when the project reaches that phase, design for:

- user identity
- organization identity
- roles/permissions
- tenant isolation
- ownership of data
- organization-level settings
- audit history

But do NOT implement this prematurely.

Do not build the full SaaS account system while the source-data pipeline is still incomplete.

---

# 22. DOCUMENTATION AND PROGRESS

`PROGRESS.md` is the main project progress document.

Do NOT create a new progress/report file for every step.

After each meaningful completed step:

1. update PROGRESS.md
2. record what changed
3. record validation performed
4. record failures/blockers
5. record the next exact step

Do not claim a feature is complete unless it is actually validated.

Keep documentation synchronized with the real repository.

---

# 23. FILE CREATION RULE

Create a new file only when it has a real purpose.

Before creating a file, check whether an existing file should be extended instead.

Avoid:
- duplicate reports
- duplicate scripts
- duplicate configs
- unnecessary wrappers
- temporary files left behind
- alternate implementations that are never used

Temporary files must be cleaned up.

---

# 24. DEPENDENCY RULE

Do not add a package merely because it is popular.

For every meaningful new dependency:

- explain why it is required
- verify it is compatible with the existing environment
- prefer mature, maintained packages
- avoid dependency duplication
- update dependency documentation/configuration appropriately

Do not replace the existing stack without a real technical reason.

---

# 25. ERROR HANDLING

Errors must be explicit and actionable.

Bad:
- silently continue
- swallow exceptions
- print PASS despite partial failure
- mark failed data as processed
- hide missing files

Good:
- identify the exact failure
- preserve state safely
- report what failed
- report what remains valid
- allow recovery
- make reruns safe

---

# 26. IMPLEMENTATION LOOP

For EVERY major step, follow:

## STEP A: INSPECT
Read the relevant existing code/data/configuration.

## STEP B: UNDERSTAND
Explain what the current implementation does.

## STEP C: GAP ANALYSIS
Identify exactly what is missing or broken.

## STEP D: PLAN
Propose the smallest correct implementation.

## STEP E: IMPLEMENT
Change only the required files.

## STEP F: VALIDATE
Run relevant tests/validators.

## STEP G: REVIEW
Check for regressions, security issues, data integrity issues, and unnecessary complexity.

## STEP H: DOCUMENT
Update PROGRESS.md.

## STEP I: STOP
Do not automatically jump to the next phase until the current phase is verified.

---

# 27. COMMUNICATION RULE

Before making a major architectural change, explain:

- current state
- problem
- proposed change
- why it is necessary
- files affected
- validation plan

Do not make large silent changes.

If an existing implementation is questionable but not blocking, document it instead of rewriting it unnecessarily.

---

# 28. DO NOT CHASE PERFECTION BACKWARDS

The project should move forward.

If an old component has a non-critical imperfection:
- document it
- assess impact
- do not rebuild it unnecessarily

Only go backwards when:
- correctness is compromised
- security is compromised
- data integrity is compromised
- the next stage cannot work safely
- the current behavior contradicts the locked workflow

---

# 29. DEFINITION OF DONE

A phase is DONE only when:

- implementation exists
- relevant data/code is present
- validation passes
- tests pass where applicable
- failure behavior is understood
- no known blocking issue remains
- provenance/integrity is preserved
- PROGRESS.md is updated

"Code written" is NOT the definition of done.

---

# 30. FIRST TASK AFTER RECEIVING THIS INSTRUCTION

DO NOT start coding immediately.

First perform the COMPLETE PROJECT AUDIT.

The audit must answer:

1. What is the current repository structure?
2. What has already been completed?
3. What has been validated?
4. What remains incomplete?
5. What is actually broken?
6. Which problems are blockers?
7. What is the current exact continuation point?
8. What should be the next implementation step?
9. What files should be changed for that step?
10. What validation will prove the step is complete?

Then STOP and present the audit.

Do not begin implementation until the audit is complete and the continuation point is established.

---

# 31. FINAL NON-NEGOTIABLE RULES

1. EXISTING PROJECT FIRST.
2. AUDIT BEFORE CODING.
3. DO NOT REBUILD FROM SCRATCH.
4. CONTINUE FROM THE CURRENT VERIFIED STATE.
5. DAILY UPDATE IS THE CURRENT CONTINUATION AREA.
6. DO NOT RESTART DATA CLEANING UNLESS AUDIT PROVES IT IS NECESSARY.
7. PRESERVE VALID EXISTING WORK.
8. NEVER DELETE SOURCE DATA TO MAKE TESTS PASS.
9. NEVER FABRICATE TAX DATA.
10. NEVER HIDE VALIDATION FAILURES.
11. NEVER ADVANCE PROCESSING STATE AFTER A FAILED PIPELINE RUN.
12. FOLLOW THE LOCKED WORKFLOW.
13. FOLLOW THE PROVIDED WORKFLOW IMAGE.
14. PRODUCTION-ORIENTED, NOT MVP-ONLY.
15. PRODUCTION DOES NOT MEAN OVERENGINEERING.
16. USE THE SIMPLEST CORRECT ARCHITECTURE.
17. SECURITY AND PRIVACY ARE CORE REQUIREMENTS.
18. TAX ANSWERS MUST EVENTUALLY BE SOURCE-GROUNDED.
19. VALIDATE EVERY MEANINGFUL STEP.
20. UPDATE PROGRESS.md AFTER MEANINGFUL COMPLETION.
21. DO NOT CREATE UNNECESSARY FILES.
22. DO NOT SILENTLY CHANGE ARCHITECTURE.
23. DO NOT JUMP AHEAD.
24. DO NOT GO BACKWARDS WITHOUT A REAL BLOCKER.
25. WHEN UNCERTAIN, INSPECT THE EXISTING PROJECT BEFORE ASSUMING.

## END OF MASTER INSTRUCTIONS
