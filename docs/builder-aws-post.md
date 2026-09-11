# Agents for Humans: Page 47 watches the public record while nobody is watching

Page 47 began with a simple question: what would a resident need if a public
meeting packet changed after they stopped looking?

The answer was not another civic search box. It was a watch that keeps a record
of what it observed, checks how a matter was presented over time, and asks a
second reviewer to challenge the interpretation before an alert reaches a
resident.

## The human problem

Residents can care about a neighbourhood without having time to read every
meeting agenda, consent calendar, attachment, and revised packet. Public
records are often technically available but practically difficult to follow.
The latest document alone also cannot show whether the title, placement, or
supporting attachment looked different at an earlier meeting.

Page 47 is for residents, neighbourhood groups, local journalists, and civic
organisations. The resident chooses a city and area once. Page 47 keeps
checking the configured public record, saves the evidence it sees, and sends a
short review only when the evidence policy allows it.

The resident does not need to keep the page open. The watch is stored on the
server and can be stopped through a private management link.

## Observation comes before interpretation

The most important design decision was to preserve the public response before
asking a model to explain it. Each capture records the source URL, UTC capture
time, HTTP status, response bytes when available, SHA-256 hash, ETag when
supplied, and explicit failures.

That makes a replaced PDF visible even when its URL stays the same. It also
keeps Page 47 honest about the difference between a transition it captured and
a history reconstructed from records that are only available today.

The application uses four evidence positions:

- **Observed by Page 47:** both versions were captured by the service.
- **Reconstructed from public record:** earlier and later records are available,
  but Page 47 did not witness the transition.
- **Current public record:** the claim describes only what is available now.
- **Cannot determine:** the record is not sufficient for a directional claim.

The last category is a product feature, not an error state. A civic system that
turns missing history into certainty is less useful to the people who rely on
it.

## Deterministic semantics protect the resident

Page 47 compares presentation dimensions independently. It does not produce a
single risk number.

The comparator returns:

- `clearer`;
- `less_clear`;
- `mixed` when supported dimensions move in opposite directions;
- `unchanged` only when enough comparable dimensions are neutral; or
- `cannot_determine` when the evidence is insufficient.

This matters in ordinary cases. If a title becomes less specific while agenda
placement becomes more visible, those directions must not cancel into
`unchanged`. If a city's last-modified field does not establish public
publication time, Page 47 abstains from a timing claim.

These rules are deterministic, tested, and kept separate from the model-based
investigation.

## A graph that can argue against itself

Page 47 uses a five-role Strands graph:

1. **Archivist** reads the stored matter history and anchors observations to
   captured records.
2. **Substance** reads only captured document pages and reports concrete
   provision changes.
3. **Process** examines titles, bodies, agenda placement, order, and supported
   process facts.
4. **Skeptic** reviews the three branches and can reject a plausible but
   unsupported interpretation.
5. **Brief Writer** uses only accepted observations to write a short resident
   brief with primary-source links and no more than three questions.

The roles have different evidence access on purpose. Substance cannot inspect
the title or agenda placement. Process cannot read attachment text. The Skeptic
cannot add facts or links. This gives the final brief a traceable boundary: the
writer can only use what survived the review.

Government documents are untrusted input. Extracted text is evidence data,
never instructions. Commands, role changes, tool requests, and behavioral
instructions embedded in a PDF are treated as document content. The controlled
fixture includes instruction-like text to keep this boundary testable.

## Why AWS services fit the job

- **Amazon Lightsail** runs the public service, scheduled collector, SQLite
  record store, and captured evidence for the deployment.
- **Amazon Bedrock** provides the document, process, review, and brief-writing
  model calls.
- **Amazon Bedrock AgentCore Runtime** hosts the deployed Strands graph for a
  managed investigation execution.
- **AWS Distro for OpenTelemetry** instruments the runtime before the graph
  loads.
- **Amazon CloudWatch** receives service logs and tracks collector completion
  with a missed-run alarm.
- **Amazon SES** delivers transactional evidence-linked review alerts.
- **AWS Systems Manager** supplies deployment parameters without putting
  credentials in source code.

The managed runtime completed a real stored Seattle review and retained a
searchable OpenTelemetry trace. The trace is recorded with the related audit,
matter, runtime, and UTC execution details so observability is evidence rather
than a control-plane status claim.

## What we evaluated

We kept the evaluation layers separate.

The real Seattle export contains 100 matters evaluated across four arms. All
four arms surfaced zero cases, and Page 47 returned `cannot_determine` for all
100. The existing 30-case human audit remains unchanged; all 30 historical gold
labels are `cannot_determine`. This is evidence that the system abstains when
the available public history cannot support a conclusion. It is not a claim of
directional accuracy.

The controlled fixture contains 28 frozen transformations with known expected
states. Page 47 produced 28/28 expected comparator states, including mixed
directions, reversal cases, abstentions, same-URL replacement hashes, duplicate
copies, unsupported-motive cases, and instruction-like document content. Two
directional reversal pairs were correct in both directions. The deterministic
fixture is a behavior check, not a real-world model score.

The repository includes the inputs, outputs, validators, independent review,
and limitations so the numbers can be inspected in context.

## The resident-facing finish line

The product is successful when a resident can:

1. understand the promise in seconds;
2. choose an area without learning the city's internal committee structure;
3. close the browser and know the watch continues;
4. open a finding that leads with what changed;
5. see each dimension and its evidence separately;
6. see what the Skeptic rejected and why;
7. click the exact public record or captured page; and
8. stop the watch without creating an account.

Page 47 does not tell residents what position to take. It helps them notice
when the public record deserves another look and gives them questions grounded
in the record.

## Lessons

The strongest lesson was that restraint is part of the feature set. It is easy
to make a civic product sound powerful by claiming intent, certainty, or broad
accuracy. It is harder—and more useful—to preserve what was actually observed,
show the evidence boundary, retain rejected interpretations, and say when the
record is not enough.

The second lesson was that evaluation and product design must meet at the
finding page. A strong comparator and a saved trace do not help a resident if
the interface hides the dimensions, evidence origin, and reasons for rejection.
The final work therefore focuses on making the resident path as clear as the
backend proof.

## Explore the build

- Live demo: https://page47.xcover.online/
- Source: https://github.com/Jennycruzy/Page47
- Architecture: https://github.com/Jennycruzy/Page47/blob/main/docs/architecture.md
- Evaluation review: https://github.com/Jennycruzy/Page47/blob/main/docs/audits/evaluation-independent-review.md
- Observability audit: https://github.com/Jennycruzy/Page47/blob/main/docs/audits/observability.md

Suggested tags: `Agents for Humans`, `civic tech`, `AWS`, `Strands`,
`AgentCore`, `public records`, `transparency`.
