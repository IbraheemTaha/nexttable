Tasks are GitHub issues
Commit regularly


Background

docs/decisions.md - the calls already made, with reasons. Read it before grooming or implementing, and do not reopen a decision without changing it there first
docs/outdated/ holds the plan, architecture, and original task list. They are reference, not the backlog - where they disagree with decisions.md or an issue, they lose


Orchestrator

The main session is the orchestrator. It launches the PM, the engineer
and QA as subagents. It does not groom, implement or test itself.

Lifecycle

1. Pick the next open issue from the backlog
2. PM grooms it
3. Engineer implements it
4. QA verifies it
5. On FAIL, back to step 3 with the QA comment as input
6. On PASS, close the issue
7. Repeat until the backlog is empty

Rules

- Do not skip step 2
- The engineer does not close the issue
- QA does not fix the code, only outputs PASS or FAIL
- The orchestrator closes the issue only after QA outputs PASS


Roles

- PM - grooms a task before anyone implements it, follows docs/team/pm.md
- Engineer - implements one groomed task, follows docs/team/sw-eng.md
- QA - checks the result against the acceptance criteria, follows docs/team/qa-eng.md
