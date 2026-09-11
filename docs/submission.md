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
| Architecture | `https://github.com/Jennycruzy/Page47/blob/main/docs/architecture.svg` (diagram) · `https://github.com/Jennycruzy/Page47/blob/main/docs/architecture.md` (details) |
| License | MIT: `https://github.com/Jennycruzy/Page47/blob/main/LICENSE` |
| Demo video | **TODO: paste public video URL; maximum 5 minutes** |
| AWS Builder ID | **TODO: paste the submitting Builder ID** |
| Builder.aws post | **TODO: paste the published post URL after publication** |

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
- [ ] Architecture diagram opens at `docs/architecture.svg`; detailed Mermaid/source explanation is in `docs/architecture.md`.
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
