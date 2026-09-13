Tasks are GitHub issues
Commit regularly


Background

docs/decisions.md - the calls already made, with reasons. Read it before grooming or implementing, and do not reopen a decision without changing it there first
docs/outdated/ holds the plan, architecture, and original task list. They are reference, not the backlog - where they disagree with decisions.md or an issue, they lose


Orchestrator

The main session is the orchestrator. It launches the PM, and the engineer as subagents. It does not groom, implement or test itself.

Lifecycle

1. Pick the next open issue from the backlog
2. PM grooms it
3. Engineer implements it
4. Close the issue
5. Repeat until the backlog is empty

Rules

- Do not skip step 2
- The engineer does not close the issue
- The orchestrator closes the issue only after Engineer finish implementation


Roles

- PM - grooms a task before anyone implements it, follows docs/team/pm.md
- Engineer - implements one groomed task, follows docs/team/sw-eng.md
