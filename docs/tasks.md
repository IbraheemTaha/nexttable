# NextTable MVP Backlog

## 1. Project Setup: Settings, SQLite, and Data Access Strategy
Goal: Get the Django project runnable, configured, and connected to SQLite, with a documented data-access approach.
Description: Confirm the Django test runner works with a minimal smoke test. Configure project settings for the chosen stack (Python, Django, SQLite, Django templates, htmx, Tailwind CSS), including environment-based secrets, debug mode, allowed hosts, database connection, static files, and timezone. Configure the database to use SQLite for local development and verify migrations can connect. Document whether SQLAlchemy will be used for core persistence, isolated data-access services, or deferred, including the reasoning, so future database changes remain intentional.

## 2. Add Base Layout And Static Asset Pipeline
Goal: Create the shared frontend foundation for all pages.
Description: Add a base Django template with common page structure, static asset loading, htmx loading, and Tailwind CSS output. Include enough styling structure for guest, staff, and manager screens to share a consistent foundation.

## 3. Define Restaurant Settings Model
Goal: Store single-restaurant configuration.
Description: Create a model for restaurant-level settings such as restaurant name, grace period, current check-in token rules, and check-in behavior. Because the MVP supports one restaurant only, include a simple way to retrieve the active settings record.

## 4. Implement Staff Roles And Authentication
Goal: Represent Staff and Manager roles, and let them log in and out.
Description: Extend or associate Django users with one of the two MVP roles: Staff or Manager. Add helper checks or permissions so views can clearly restrict manager-only actions. Add login and logout views using Django authentication, and protect staff and manager pages so unauthenticated users cannot access operational screens.

## 5. Create Manager Staff Account Management
Goal: Let managers manage staff accounts.
Description: Add manager-only screens for listing staff users and creating or editing staff accounts. Keep role choices limited to Staff and Manager.

## 6. Define Table Model
Goal: Store restaurant tables and their operating status.
Description: Create a table model with table name or number, seating capacity, and current status. Support the MVP statuses Free, Reserved, Occupied, and Cleaning.

## 7. Create Manager Table Configuration
Goal: Let managers maintain the restaurant table list.
Description: Add manager-only screens for creating, editing, and removing tables. Validate capacity and prevent changes that would break active table assignments.

## 8. Define Waitlist Entry Model With Audit Timestamps
Goal: Store guest check-ins, lifecycle status, and key lifecycle timestamps.
Description: Create a waitlist entry model with guest name, party size, optional contact and preference fields, lifecycle status, check-in time, priority metadata, and assigned table. Include statuses such as Waiting, Notified, Arrived, Seated, Late/Demoted, Cancelled, No-show, and Left. Store timestamps for check-in, notification, arrival, seating, cancellation, no-show, and leaving where applicable, to support staff visibility and future analytics without building analytics now.

## 9. Add Waitlist Entry Validation
Goal: Enforce required guest fields and valid values.
Description: Validate that guest name and party size are required, party size is positive, and optional preference fields use supported values. Add model or form tests for the required validation behavior.

## 10. Implement Daily Check-In Token Generation
Goal: Support a daily-changing QR/URL token.
Description: Add logic to generate or resolve the current check-in token for the restaurant day. Old tokens should not remain valid indefinitely, and the implementation should be simple enough for the MVP.

## 11. Build Guest Check-In Page
Goal: Let guests join the waitlist from the current QR/URL.
Description: Create the public check-in page using the daily token. The form must collect guest name and party size, and may collect optional phone number, indoor/outdoor preference, seating preference, accessibility requirements, high chair, and notes.

## 12. Create Guest Check-In Submission Flow
Goal: Save a valid guest check-in and redirect to the waiting page.
Description: Process the check-in form, create a waitlist entry, assign an initial estimated wait range, and redirect the guest to their private waiting/status page. Handle invalid or expired check-in tokens with a clear error state.

## 13. Build Guest Waiting Page With Auto-Refresh And Cancellation
Goal: Show guests their current waitlist status, keep it live, and let them cancel.
Description: Create a guest-facing status page that displays current status, estimated wait range, cancellation option, and table-ready message when applicable, without showing exact queue position. Use htmx polling or partial refreshes to update the status area, table-ready notification, and estimated wait range without manual refresh. Add a cancellation action that confirms and updates the waitlist entry status without deleting historical data.

## 14. Define ETA Rules And Manager Configuration
Goal: Store and let managers configure manager-configurable wait estimate rules and grace period.
Description: Create a simple rules model for party-size-based wait estimates, supporting ranges such as 1-2, 3-4, and 5+ guests while leaving room for future smarter estimation. Add manager-only screens for editing these ETA rules and the notified guest grace period, validating that wait ranges and grace period values are positive and operationally reasonable.

## 15. Implement Wait Estimate Calculation
Goal: Calculate an estimated wait range for a guest.
Description: Add a service that estimates wait time using party size, current queue, and compatible table availability. Keep the algorithm intentionally simple and covered by tests.

## 16. Define Table Compatibility Rules
Goal: Determine whether a table can seat a waiting party.
Description: Add a service that checks table capacity and guest requirements such as accessibility, indoor/outdoor preference, seating preference, and high chair needs. Include tests for compatible and incompatible cases.

## 17. Implement Queue Priority Selection
Goal: Select the oldest eligible compatible guest.
Description: Add a service that ranks eligible waiting parties for a free table. The primary rule should be oldest eligible check-in wins, with demoted guests ranked behind normal waiting guests.

## 18. Implement Automatic Table Matching
Goal: Assign the best waiting guest when a table becomes Free.
Description: When a table status changes to Free, find compatible waiting parties, select the highest-priority guest, assign the table, mark the guest Notified, and set the table to Reserved. Cover the full transition with tests.

## 19. Build Staff Dashboard Shell
Goal: Provide the main authenticated staff workspace.
Description: Create the staff dashboard page with navigation between waitlist and table views, or a combined view if simpler. The dashboard should be available to both Staff and Manager users.

## 20. Build Staff Waitlist View
Goal: Show staff the active guest queue.
Description: Display guest name, party size, estimated wait, check-in time, preferences, requirements, status, and assigned table when present. Include enough ordering and filtering to make active operations easy to scan.

## 21. Add Staff Guest Status Actions And Seated/Left Side Effects
Goal: Let staff move guests through their lifecycle and keep table state synchronized.
Description: Add actions for marking a guest Arrived, Seated, Left, Cancelled, No-show, or manually adjusting status when necessary, enforcing valid lifecycle transitions and recording the important timestamps. When staff marks a guest Seated, update the assigned table to Occupied; when staff marks a seated guest Left, update the table to Cleaning and preserve the guest history.

## 22. Build Staff Table Status View
Goal: Show staff all restaurant tables and current state.
Description: Display each table with name or number, capacity, status, and current assigned or seated party. Make the view easy to scan during service.

## 23. Add Staff Table Status Actions
Goal: Let staff update table status manually.
Description: Add actions to move tables between Free, Reserved, Occupied, and Cleaning where valid. When a table becomes Free, trigger the automatic matching logic.

## 24. Implement Manual Table Assignment Override
Goal: Allow staff to override automatic matching.
Description: Add a staff action to assign or reassign a compatible table to a waiting guest. Validate the table and guest state, then update guest status and table status consistently.

## 25. Implement Late Guest Demotion
Goal: Demote notified guests after the grace period expires.
Description: Add logic that detects Notified guests past the configured grace period and moves them into the Late/Demoted state. The guest should not be deleted, and their future priority should be lower than normal waiting guests.

## 26. Add Operational Refresh To Staff Dashboard
Goal: Keep staff views current without full manual refresh.
Description: Use htmx polling or targeted partial updates for the waitlist and table status areas. Keep updates simple and avoid introducing websockets for the MVP.

## 27. Add Basic Access Control Tests
Goal: Verify guest, staff, and manager access boundaries.
Description: Add tests proving public guest pages are reachable as intended, staff pages require login, and manager-only pages reject Staff users. Keep the tests focused on MVP permissions.

## 28. Add Core Business Rule Tests
Goal: Protect the most important waitlist and table rules.
Description: Add tests for required guest fields, oldest eligible guest priority, table compatibility, automatic matching, grace-period demotion, and table lifecycle side effects. These tests should cover the rules most likely to cause operational problems if broken.

## 29. Create Seed Data For Local Development
Goal: Make local demos and manual testing easy.
Description: Add a fixture or management command that creates one restaurant settings record, sample staff users, ETA rules, and sample tables. Avoid creating production-only assumptions in the seed data.

## 30. Document Local Development Workflow And Deployment Checklist
Goal: Give contributors a clear way to run the MVP locally, and capture what must be true before production use.
Description: Add documentation for installing dependencies, configuring environment variables, running migrations, starting the server, building frontend assets, and running tests, kept aligned with the chosen stack and current project commands. Also document required environment variables, database migration steps, static file handling, admin account setup, allowed hosts, HTTPS expectations, and backup considerations as a checklist rather than a full deployment platform decision.

## 31. Perform End-To-End MVP Workflow Test
Goal: Verify the full restaurant waitlist flow works together.
Description: Manually test guest check-in, waiting page updates, automatic table assignment, arrival, seating, leaving, cleaning, and returning a table to Free. Record any issues found and confirm the critical workflow is faster than doing the same work manually.
