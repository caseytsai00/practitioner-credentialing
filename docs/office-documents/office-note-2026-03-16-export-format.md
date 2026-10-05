# How this office exports its credentialing records

Larkhollow Community Hospital · Medical Staff Office. A note from the Medical Services Professional to whoever automates the initial-appointment file. Written 2026-03-16, alongside the first export.

I run the export from the credentialing database every few weeks and drop it in the shared folder, one sub-folder per export. Here is what you get, what the columns mean, and the three or four things that catch people out.

## The export date is the clock

Every batch folder has a README.md that says the **export date** and the window it covers. That date is the clock for everything in the folder: **nothing in a batch happened after its export date.** Work the batch as if today were the export date. Do not use the real date you run your tool, and do not carry today's date into an arithmetic that a batch is supposed to settle.

The three exports are 2026-03-16, 2026-04-20 and 2026-05-18. The first one covers everything on file up to and including 2026-03-15, however far back it goes — one application here was first received in 2024. The second and third cover only what changed since the previous one.

The caseload at an export date is every application file the office has received up to that date, however that file ended. A withdrawn or discontinued file stays in the caseload with its final status; a later batch never removes a file, it only adds to what is known about it.

## A batch is closed. It never changes.

I never go back and edit an export. If an applicant corrects something, a **new revision** of the application appears in a later batch and the old one stays exactly where it was. If a board sends a corrected reply, the corrected reply is a **new row** and the old row stays. If a committee decides something twice, there are two decision records.

So: do not diff a later batch against an earlier one looking for edits. There are none. What a later batch contains is new rows, new documents and new observations.

## The files

Thirteen comma-separated exports, and three folders of documents.

| File | One row is |
| :-- | :-- |
| applications.csv | an application revision I received in the window |
| application-disclosures.csv | one professional practice question and the applicant's answer |
| declared-history.csv | one history entry the applicant declared |
| declared-credentials.csv | one licence or certification as the applicant described it |
| privilege-requests.csv | one privilege group requested |
| licence-lookup-wa.csv | one Washington credential record from the state board's lookup |
| licence-lookup-other-states.csv | one out-of-state credential record |
| certification-replies.csv | one certifying board's reply |
| verification-replies.csv | one reply about education and training, or about an affiliation or employer |
| verification-attempts.csv | one request I sent |
| peer-referees.csv | one referee named on an application, or supplied later |
| peer-reference-replies.csv | one completed reference form that came back |
| correspondence.csv | one letter, memo or decision record, with the path to the document |

| Folder | What is in it |
| :-- | :-- |
| letters/ | applicants' explanation letters, withdrawals, referee substitutions, and my own written requests for missing items |
| dispositions/ | the Clinical Director's recorded dispositions |
| decisions/ | Credentials Committee and Executive Committee minutes extracts, and Governing Body approval records |

correspondence.csv is an index. It tells you the documents exist and where they are. It does not tell you what they say — you have to open them.

A file with only a header row means the export ran and there was nothing in that window. That is not the same as a missing file, and it is not an error.

## Dates, blanks and columns

- **Dates** are YYYY-MM-DD. Always. A date range is inclusive at both ends: an entry from_date 2022-01-01, to_date 2022-12-31 covers the 1st of January and the 31st of December. An expiry date is the last day the credential is valid.
- **An empty cell means I hold no value for that field.** It does not mean zero, it does not mean "no", and it does not mean the answer is unknown-but-probably-fine. Two blanks carry a specific meaning and you should learn them:
  - a blank to_date in declared-history.csv means **the entry is current**, running to the export date — not that the end date is missing;
  - a blank expiry_date in certification-replies.csv means the certificate **does not expire** — some older certificates are time-unlimited.
- **No money appears anywhere.** We do not record fees, salaries or contract values in the credentialing file.
- Files are UTF-8 with Unix line endings. Values are quoted only when they contain a comma.

## The three joins that matter

1. **Everything on the applicant side joins on application_id**, and on revision where the fact belongs to a revision. Entries, credentials, privilege requests and disclosures all restate on each revision, so always filter to the revision you are working.
2. **The Washington board export carries no practitioner identifier.** It never has. I join it to an application on lastname, firstname, middlename and birthyear. I have checked that no two rows in any one export share those four values, so the join gives you at most one row. **An applicant with no row in that file holds no Washington credential.** The absence is the answer, not a data problem.
3. **A referee with no row in peer-reference-replies.csv has not replied.** Silence produces no record. You can see it only by looking at the requests in verification-attempts.csv and finding no reply against them.

## The Washington export's own columns

I pass that file through as the board publishes it and add one column. The board's twelve are credentialnumber, credentialtype, status, firstissuedate, lastissuedate, expirationdate, ceduedate, actiontaken, birthyear, firstname, middlename, lastname. Mine is lookup_date — the day I ran the lookup. It is my own act, not a source's reply, so the usability window is not applied to it.

Two of the board's columns are easy to misread:

- **ceduedate is a continuing-education due date.** We do not use it. Continuing education is handled outside this procedure and it has nothing to do with whether a licence is valid.
- **actiontaken says the board has acted. It does not say what the action was.** For that you need the board's written reply, which arrives as a document, not in this file. A Yes here is a reason to go and read; it is not a conclusion.

The first export carries the board's whole file for our county — 435 rows — so you can see what an ordinary population looks like. The second and third carry only a re-lookup of the practitioners whose files are open, because that is all I re-run.

## How often anything is actually wrong

I want to say this plainly, because a small sample of credentialing files can leave the wrong impression.

**In the board's population, action against a credential is rare.** In the 435-row export you have: 431 rows say No, 3 say Yes, and 1 says Pending. That is 0.69% Yes and 0.23% Pending, and it is the shape of the real thing — the overwhelming majority of licensed practitioners have a clean board record, and any tool that expects otherwise will be wrong almost every time it fires.

**The applicants in these batches are a different matter, and deliberately so.** This is a teaching set. I have put every situation the procedure has a rule for into these three exports on purpose, so the run has something to exercise: a restricted licence, an unexplained gap, a school that closed, a referee who never answers, a certificate that lapsed, a decision against the wrong revision. A real nine weeks of intake would be far quieter than this. **Do not read the applicant set as a base rate.** Read it as a checklist that happens to be shaped like a caseload.

The clean files are genuinely clean. If your tool raises something on one of them, it is your tool.

## What I do not export

My own queue, my own statuses and my own conclusions. This export is the evidence, not my reading of it. What is complete, what is outstanding, what is presentable and what is owed to whom is the work — it is not in the folder, and it should not be.

**Referee addresses.** The export carries no address column for peer referees. The working-address half of completeness condition 7 is checked by my office outside the export, so a run assesses condition 7 on the named referees alone and records the address check as not assessable from the export — neither met nor failed.
