# 08 — Forms (Area I)

## I1 Form bound to a board — P1
**Story:** As Mia, I publish a "Contact us" form whose submissions become leads.
**Rules**
- I1.1 A form is a board view (D9) with: title, description, questions (ordered), target group for new items, active flag, public token (unguessable, ≥ 128-bit), settings.
- I1.2 Each question maps to exactly one column (Name is always the first question unless hidden with a default value); a column appears at most once.
- I1.3 Submission creates one item in the target group with values; the item's creator is "Form: <title>"; triggers T1 automations.
- I1.4 After submit: thank-you message (default "Thanks for submitting!"); P2: redirect URL, submit-another button.
- I1.5 Deactivated form shows "This form is no longer accepting responses".
**AC**
- AC-I1-1 Given the Leads form with Name, Company, Email, Phone, when a prospect submits valid data, then a Lead item exists in group "New Leads" with those values and is visible to all Leads viewers within 2 s, and its Status = New Lead within 5 s (automation 3).
- AC-I1-2 Given the form is deactivated, when the public URL is opened, then the closed message is shown and POST submissions are rejected (410).

## I2 Access — P1 (public link), P2 (require login, password)
- Public link usable without account; P2 adds "only account users" and password protection.
- AC-I2-1 Given an active form, when opened in a private browser window with no session, then it renders and accepts a submission; given a random token, then 404.

## I3 Questions — P1
- I3.1 Supported mapped column types P1: Name, Text, Long text, Numbers, Status (single choice shown as radio/dropdown), Dropdown (single/multi), Date, Email, Phone, Link, Checkbox, Files (≤ 5 files, 25 MB each, uploaded individually to short-lived presigned upload slots issued by the form before submit), People (P2, only for login-required forms).
- I3.2 Per question: label (defaults to column title), description, required flag, placeholder, hidden with default value, visible label subset for Status/Dropdown.
- I3.3 Server-side validation identical to column validation (C40.5) + required checks; errors returned per field.
**AC**
- AC-I3-1 Given Email is required and missing, then submission fails with field error "Email is required" and no item is created.
- AC-I3-2 Given a hidden question Lead Source = "Website form", then the created item has that value.

## I4 Conditional logic — P2; I5 Appearance — P2; I6 Close date, response limits, prefill, UTM — P3

## I7 Abuse protection — P1
- I7.1 Order of defenses per IP per form: submissions 1–5 in a minute pass; 6–10 in a minute require a passed bot challenge (AWS WAF Challenge/CAPTCHA); the 11th and later in that minute get 429. Daily cap 100 per IP per form. Thresholds configurable by owner.
- I7.2 Honeypot field on every form. Presigned upload slots count toward the I7.1 per-IP limits (max 10 slots/min); uploads not attached to a submission are purged after 24 h.
- I7.3 Payload limits: submission JSON ≤ 1 MB (files go to presigned slots, I3.1, each ≤ 25 MB, ≤ 5 per question, ≤ 100 MB per submission); text fields bounded by column limits; HTML stripped.
- AC-I7-1 Given 11 submissions from one IP within a minute, then the 11th is rejected with 429.
- AC-I7-2 Given the honeypot field is filled, then the response is 200 to the client but no item is created (logged as spam).
