# fairshift as a product

## Who it's for

Independent cafés, restaurants, bubble-tea and retail shops with **5–40
shift staff**, usually a mix of full-timers and part-timers or students.
The person building the rota is the owner or an outlet manager, typically
in a spreadsheet and a WhatsApp group.

The pain, in the order owners describe it:
1. **Time.** Hours every week fitting part-timers' availability around
   cover.
2. **Sick calls.** A no-show at 7am means phoning around, and the fix often
   breaks someone's rest day or pushes them into overtime.
3. **Cost surprises.** Overtime and public-holiday premiums found at payroll,
   not when planning.
4. **Fairness complaints.** The same people always get the closing shifts or
   the short weeks.
5. **Compliance.** Rest days and hour limits are easy to break by accident
   when a rota is edited in a hurry.

## How it can be sold

- **Subscription software:** the hosted web app per outlet per month. A
  typical price point for SMB rota tools is around S$3–6 per staff member a
  month, or a flat outlet fee. Sick-call re-planning and the compliance
  check are the paid differentiators; plain rota grids are a commodity.
- **Rota-as-a-service:** for owners who won't touch software. They send
  availability (a form or chat), and receive the rota and each person's
  message every week. The re-plan makes same-day changes a quick service
  rather than a phone marathon.
- **Compliance audit:** a one-off check of past rotas (`fairshift check`)
  ahead of an audit or a dispute.
- **Embedded engine:** POS and payroll vendors without an optimizer can call
  the API.

## What it is (and isn't yet) good for

**Ready now:**
- Building optimal weekly rotas for one outlet, up to a few hundred shifts.
- Explaining gaps.
- Minimal-change re-planning.
- Auditing.
- Exports.
- The single-user web app.

**Not yet:**
- **Accounts:** no logins or multiple outlets. The web app is single-tenant;
  run one per shop or put it behind your own auth.
- **Staff self-service:** no app for staff to enter availability or swap
  shifts. They are entered by the manager.
- **Payroll:** no integration with Xero, Talenox or Swingvox. Payroll gets a
  CSV it can import.
- **Demand forecasting:** cover needs are typed in, not learned from POS
  sales.
- **Labour law:** rules are configurable, with defaults that follow the
  Singapore Employment Act Part IV limits. It does not decide who is covered
  by Part IV, or rules like rest-day pay. It is a planning tool, not legal
  advice.

## Data and privacy

- **Personal data:** a rota holds names, availability and pay rates. Under
  Singapore's PDPA these are personal data. The app stores nothing: each
  request is solved in memory and returned.
- **Hosted version:** it would need consent wording in the staff
  onboarding, access control per outlet, and a retention period for past
  rotas.

## Roadmap

1. **Accounts and outlets:** saved shops, rota history, publish and lock.
2. **Staff links:** availability and leave requests through a link (no app
   install), and shift swaps that run through `check` before a manager
   approves.
3. **Messaging:** send the change list after a re-plan (WhatsApp Business
   API, or SMS).
4. **Forecast cover:** from POS sales per hour (CSV first), turning sales
   per labour hour into the need per shift.
5. **Payroll export:** formats for the common Singapore payroll tools.
