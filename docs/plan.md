# NextTable MVP Plan

## 1. Product Name

**NextTable**

A simple restaurant waitlist and table management tool for a single restaurant.

The MVP focuses on:
- fast guest check-in
- live wait estimation
- automatic table matching
- simple web notifications
- staff queue management
- table status tracking

---

## 2. MVP Goal

Build a lightweight restaurant waitlist manager that reduces lobby congestion, gives guests visibility into their wait, and helps staff assign tables efficiently.

The system should remain simple, easy to operate, and easy to extend later.

---

## 3. Restaurant Scope

The MVP supports:

- one restaurant
- one physical location
- individual staff accounts
- two roles: Staff and Manager

Not included in MVP:
- multiple restaurants
- branches
- multi-tenant architecture
- restaurant groups

---

## 4. Guest Check-In

Guests can join the waitlist using:

- a QR code displayed physically at the restaurant
- the URL behind the QR code directly

The QR/URL uses a daily-changing token so an old saved link cannot be reused indefinitely.

### Required guest fields

- Name
- Party size

### Optional guest fields

- Phone number
- Indoor / outdoor preference
- Seating preference
- Accessibility requirements
- High chair
- Notes

The check-in process should not require an app download.

---

## 5. Guest Waiting Page

After joining, the guest remains on a web-based waiting page.

The page should show:

- current waiting status
- estimated wait time
- table-ready notification
- cancellation option

The guest does **not** need to interact when the table becomes ready.

Staff marks whether the guest has arrived.

The MVP should show an **estimated wait range**, rather than an exact queue position.

Example:

> Estimated wait: 20–30 minutes

---

## 6. Wait-Time Estimation

For MVP, keep estimation intentionally simple.

The wait estimate is primarily based on:

- party size
- current queue
- availability of compatible tables

The initial estimation logic can use configurable party-size rules.

Example starting point:

- 1–2 guests: shorter estimated duration
- 3–4 guests: medium estimated duration
- 5+ guests: longer estimated duration

The architecture and data model should leave room for future improvements such as:

- historical dining duration
- time-of-day patterns
- table-specific turnover
- restaurant occupancy
- ML-based ETA prediction

These are **not part of the MVP**.

---

## 7. Queue Priority

The system should automatically determine queue priority.

Primary rule:

**Oldest eligible check-in wins.**

When a table becomes available:

1. Find parties compatible with the table.
2. Apply guest/table compatibility rules.
3. Rank eligible parties by queue priority.
4. Select the guest who checked in first.

Compatibility can consider:

- party size
- accessibility
- indoor/outdoor preference
- seating preference
- high chair requirements

Staff can manually override an automatic match.

---

## 8. Automatic Table Matching

When a table becomes **Free**, NextTable automatically:

1. finds compatible waiting parties
2. chooses the highest-priority eligible party
3. assigns the table
4. changes the guest status to notified
5. changes the table status to Reserved
6. shows the table-ready notification on the guest's waiting page

For the MVP, tables are independent.

The system does **not** combine multiple tables for larger groups.

---

## 9. Guest Lifecycle

Recommended guest states:

- Waiting
- Notified
- Arrived
- Seated
- Late / Demoted
- Cancelled
- No-show
- Left

Typical flow:

**Waiting → Notified → Arrived → Seated → Left**

Both guests and staff can cancel a waitlist entry.

---

## 10. Late Guest / Grace Period

When a guest is notified that a table is ready, a grace period begins.

Default example:

**30 minutes**

If the guest does not arrive within the grace period:

- the system does not delete them
- their queue priority is reduced
- they are moved to the lowest-priority group / bottom of the queue

The grace period must be configurable by a Manager.

This allows the restaurant to shorten or extend it depending on how busy the restaurant is.

Staff should be able to handle exceptional cases manually.

---

## 11. Table Management

Each restaurant table should have:

- table number / name
- seating capacity
- current status

### MVP table statuses

- Free
- Reserved
- Occupied
- Cleaning

### Table lifecycle

When a free table is assigned:

**Free → Reserved**

When staff seats the assigned party:

**Reserved → Occupied**

When the party leaves:

**Occupied → Cleaning**

The transition to Cleaning happens automatically after staff marks the party as **Left**.

After cleaning is finished, staff manually marks the table:

**Cleaning → Free**

Once a table becomes Free, automatic guest matching runs again.

---

## 12. Staff Dashboard

The host/staff dashboard should provide a single operational view.

### Waitlist view

Show:

- guest name
- party size
- estimated wait
- check-in time
- preferences / requirements
- current status
- assigned table, when applicable

Staff actions:

- mark guest Arrived
- mark guest Seated
- mark guest Left
- cancel/remove guest
- override table assignment
- adjust guest status if necessary

### Table view

Show each table with:

- table number
- capacity
- status
- current assigned/seated party

Staff can change table status manually when needed.

---

## 13. Staff Accounts and Roles

Each employee has an individual account.

### Staff

Can:

- view the queue
- manage guests
- mark guests Arrived
- mark guests Seated
- mark guests Left
- cancel guests
- change table status
- override automatic matching when necessary

### Manager

Can do everything Staff can do, plus:

- manage staff accounts
- add/edit/remove tables
- configure grace period
- configure ETA rules
- manage restaurant settings
- configure check-in / queue behavior

Keep role management limited to these two roles for the MVP.

---

## 14. Notifications

The MVP uses **web-based notifications only**.

No SMS, WhatsApp, push app, or email notifications are required.

When the guest's table is ready, their waiting page updates automatically with a clear message such as:

> Your table is ready.

The page should update without requiring the guest to manually refresh where practical.

---

## 15. Daily QR / URL

The restaurant has a check-in URL represented by a physical QR code.

The access token should change daily.

Purpose:

- discourage reuse of old check-in links
- keep check-in tied to the current restaurant day/session
- reduce remote or stale check-ins

The exact token rotation mechanism can remain simple in MVP.

---

## 16. Core MVP Screens

### Guest side

1. Check-in page
2. Waiting/status page
3. Table-ready state
4. Cancellation confirmation

### Staff side

1. Login
2. Main dashboard
3. Waitlist view
4. Table status view

### Manager side

1. Restaurant settings
2. Table configuration
3. Staff account management
4. ETA/grace-period configuration

The staff waitlist and table views may be combined into a single dashboard if that produces a simpler user experience.

---

## 17. Core Business Rules

1. One restaurant only.
2. Guests check in through the current QR/URL.
3. Name and party size are required.
4. Other guest details are optional.
5. Wait time is estimated automatically.
6. Manager-configurable rules control ETA and grace period.
7. Guests are matched only with compatible tables.
8. Among compatible parties, the oldest eligible check-in receives priority.
9. Automatic matching happens when a table becomes Free.
10. Staff can override automatic decisions.
11. Staff confirms guest arrival and seating.
12. Late notified guests are demoted rather than automatically removed.
13. Guests and staff can cancel a waitlist entry.
14. Tables remain independent in MVP.
15. A guest being seated changes their table to Occupied.
16. Marking the guest Left changes the table to Cleaning.
17. Staff marks a cleaned table Free.
18. A newly Free table triggers automatic matching again.

---

## 18. Explicitly Out of Scope for MVP

Do not build these initially:

- reservations
- multi-location support
- multi-tenant SaaS management
- combined tables
- SMS notifications
- WhatsApp notifications
- native mobile app
- POS integration
- payments
- detailed CRM / customer profiles
- loyalty program
- advanced analytics
- historical demand forecasting
- ML-based wait prediction
- sophisticated dining-duration prediction
- automated no-show scoring
- complex floor-plan editor
- advanced permissions system

These may be added later.

---

## 19. Future Expansion Room

The system should be designed so the MVP can later support:

- smarter ETA prediction
- historical restaurant analytics
- SMS / WhatsApp notifications
- reservations
- repeat-customer profiles
- table combination
- multiple locations
- POS integrations
- advanced floor management
- occupancy forecasting
- restaurant performance dashboards
- demand prediction
- ML-based queue optimization

The MVP should not implement these features now, but the database and service boundaries should avoid unnecessarily blocking them.

---

## 20. MVP Product Principle

The main product principle for NextTable is:

**Keep restaurant operations faster than doing the same job manually.**

Every MVP feature should therefore pass three tests:

1. Is it necessary for the core waitlist workflow?
2. Does it reduce work for staff or uncertainty for guests?
3. Can it be implemented without making the first version unnecessarily complex?

If not, defer it until after the MVP.
