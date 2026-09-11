# Page 47 submission kit

This is the copy-ready package for the Agents for Humans hackathon submission.
Replace the two placeholders for the demo video and AWS Builder ID before
submitting.

## Submission title

**Page 47 — When the packet changes, residents should know**

## One-sentence pitch

Page 47 watches public meeting records for the places residents care about,
checks when a matter's presentation changes, and alerts them only when the
change survives an evidence review.

## Copy-ready text description

Residents should not need to monitor every council agenda, consent calendar,
attachment, and revised packet to stay informed about the places they care
about. Page 47 lets a resident choose a city and area once, then keeps checking
the public record while they are away.

Page 47 captures public records and document versions, compares how the same
matter appeared across meetings, and investigates each supported change through
distinct evidence roles. Its comparator reports `clearer`, `less_clear`,
`mixed`, `unchanged`, or `cannot_determine`; it never hides opposing evidence in
an opaque score. Archivist, Substance, and Process readers gather separate
evidence, the Skeptic can reject unsupported interpretations, and the Brief
Writer turns surviving observations into a short plain-language review with
primary-source links and questions worth asking.

The product is built for residents, neighbourhood groups, local journalists,
and civic organisations. Seattle is the deep deployment; Denver proves that
the same flow works through a separate city adapter. AWS services include
Lightsail, Bedrock, AgentCore Runtime, ADOT/OpenTelemetry, CloudWatch, SES, and
Systems Manager.

Page 47 does not infer intent, make a legal finding, or tell residents what
political position to take. When the available history is insufficient, it says
so. The repository preserves the 30-case historical abstention audit, a
28-case controlled directional evaluation, an independent evaluation review,
and a retained searchable managed-runtime trace.

## Required links

| Submission field | Value |
| --- | --- |
| Public code repository | `https://github.com/Jennycruzy/Page47` |
| Live demo | `https://page47.xcover.online/` |
| README | `https://github.com/Jennycruzy/Page47#readme` |
| Architecture | `https://github.com/Jennycruzy/Page47/blob/main/docs/architecture.md` |
| License | MIT: `https://github.com/Jennycruzy/Page47/blob/main/LICENSE` |
| Demo video | **TODO: paste public video URL; maximum 5 minutes** |
| AWS Builder ID | **TODO: paste the submitting Builder ID** |
| Builder.aws post | **TODO: paste the published post URL after publication** |

## Five-minute demo script

Keep the recording under five minutes. Use the live site and stored public
records; do not create a fictional finding for the demo.

### 0:00–0:25 — Problem

“Public decisions can live across hundreds of pages and multiple meetings. A
packet can change while the people affected by it are not watching.”

Show the Page 47 homepage.

### 0:25–0:45 — Product

“Page 47 watches that record for residents. I choose an area once, and the
watch continues on the server.”

Point to the resident promise and the evidence-first trust line.

### 0:45–1:10 — Create a watch

Create a Seattle watch with an area and the verified demo mailbox. Submit it.
Show the confirmation state and say:

“I can close this page now. Page 47 keeps watching.”

Show the private management link and stop-watch control without stopping the
demo watch yet.

### 1:10–1:35 — Show capture history

Open a stored matter and show the earlier and later captured records, source
links, capture times, and hashes.

### 1:35–2:15 — Show a stored review

Open the strongest genuine stored review from the homepage. Clearly label it as
a review of captured public records, not a live event.

### 2:15–2:45 — Show dimensions

Show the title, agenda placement, document substance, and timing sections as
separate evidence dimensions. Point out any unavailable dimension rather than
skipping it.

### 2:45–3:20 — Show the investigation

Show the five roles: Archivist, Substance, Process, Skeptic, and Brief Writer.
Explain that the first three gather different evidence and the Skeptic can
prevent a weak interpretation from surfacing.

### 3:20–3:45 — Show the Skeptic boundary

Open the rejected-observation section. Read one rejection reason and explain
that a plausible story is not published without direct support.

### 3:45–4:15 — Show the resident alert

Open the delivered email from the verified demo path, then follow its link to
the finding and exact evidence page.

If SES production access is still pending, say that the controlled mailbox is
verified and that the web finding is independently available.

### 4:15–4:35 — Show resident action

Show the three evidence-backed questions. Explain that Page 47 informs the
resident without telling them how to vote or what position to take.

### 4:35–4:45 — Show portability

Show Denver in the city selector or architecture diagram. Say:

“Seattle is the deep deployment. Denver proves the model is not hard-coded to
one city.”

### 4:45–5:00 — Close

“Page 47 does not tell residents what to think. It makes sure they know when
the public record deserves another look.”

## Rubric crosswalk

### Problem, users, and impact

Page 47 reduces the effort required to follow a local public matter. The
resident chooses an area, receives an evidence-linked review, and gets useful
questions instead of a political instruction. The README explains the user,
the problem, and the limits of the claim.

### Technical implementation

The repository contains the application, city adapters, scheduled collector,
append-only capture records, deterministic comparator, five-role Strands graph,
AgentCore deployment, ADOT instrumentation, CloudWatch checks, SES delivery
path, tests, setup commands, and dated audits.

### Appropriate use of agents

The task is ongoing and evidence-heavy. The graph separates document reading,
process reading, evidence review, and brief writing. The Skeptic is a distinct
veto step. This is a reasoned use of agents rather than a chat interface placed
over a static page.

### Design and usability

The first action is to watch an area. The user does not need to know the city's
internal committee structure. The service stores the watch server-side, offers
a private management link, explains the evidence state, and provides a stop
control.

### Trust and safety

Page 47 distinguishes observed, reconstructed, current, and undetermined
evidence. It refuses motive claims, keeps opposing directions as `mixed`,
abstains when history is missing, treats public documents as untrusted data,
and retains rejected interpretations for inspection.

### Originality

The key product primitive is forward observation of presentation changes. Page
47 does not only retrieve the latest document; it preserves what it saw, shows
how a matter was presented before and after, and asks an independent reviewer
whether the interpretation survives.

### Portability and completeness

Seattle provides depth and Denver provides a second city adapter. The final
package includes a live URL, public source code, visible MIT license, README,
architecture diagram, demo plan, tests, evaluation artifacts, and limitations.

## Submission checklist

- [ ] Repository visibility is **Public**.
- [ ] `README.md` leads with the product and live demo.
- [ ] `LICENSE` is MIT and visible in the repository.
- [ ] Architecture diagram renders from `docs/architecture.md`.
- [ ] Demo video is public and no longer than five minutes.
- [ ] Video covers the problem, users, why it matters, and the working product.
- [ ] AWS Builder ID is entered in the submission form.
- [ ] Builder.aws post is published publicly before submission, if claiming the
      bonus.
- [ ] Live URL, repository URL, video URL, and post URL are tested in a private
      browser window.
- [ ] No secrets, private keys, mailbox contents, or host credentials appear
      in the repository or recording.
- [ ] Claims in the form match the dated evaluation and operational audits.
- [ ] SES wording reflects the actual account status on submission day.

## Claims to avoid

Do not claim that Page 47 detects corruption, proves bad intent, or predicts
policy outcomes. Do not call the 30 historical cases a directional accuracy
benchmark. Do not turn the 28 controlled cases into a real-world percentage.
Do not claim arbitrary email delivery until SES production access is approved.
Do not claim that every model interpretation is correct; the product's value is
that unsupported interpretations can be rejected and uncertainty remains
visible.
