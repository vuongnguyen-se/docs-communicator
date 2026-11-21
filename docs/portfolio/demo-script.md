# Demo session: screenshots and video

One deploy session, about an hour and a few cents (see `cost-notes.md`). Use only the fictional PDFs from `eval/make_pdfs.py` (`nimbus-handbook.pdf`, `sen-vang-so-tay.pdf`) so that nothing personal appears on screen.

## Before recording

1. `scripts\deploy.ps1 -AlarmEmail <owner email>` and confirm the SNS subscription email.
2. Create the PDFs: `python eval/make_pdfs.py <folder>`. Also make a text file renamed `fake.pdf`.
3. Browser: a clean window at 1440 × 900, zoom 100%, no bookmarks bar or extensions visible. Sign in once, so the "set a new password" step doesn't appear on camera.
4. Hide anything personal: the email address in the browser profile, and other tabs.

## Shot list (save as `docs/portfolio/screenshots/NN-name.png`)

| # | Screen | What it shows |
|---|---|---|
| 01 | Sign-in page | Cognito sign-in with the brand; no self sign-up |
| 02 | Empty workspace | Documents panel and chat side by side |
| 03 | Upload in progress | One file "Checking file…", one "Indexing…" |
| 04 | Both documents Ready | Status settled with no page reload |
| 05 | English answer with its source | "When does the Nimbus team meet?" with the source chip open, showing the excerpt |
| 06 | Vietnamese answer | "Ngân sách năm 2026 của dự án Sen Vàng là bao nhiêu?" answered in Vietnamese, with its source |
| 07 | Cross-language answer | "Ai là kỹ sư trưởng của dự án Nimbus?" (Vietnamese question, English document) |
| 08 | Honest decline | "What is the capital of Australia?" gives the fixed "could not find" answer, with no sources |
| 09 | Rejected file | `fake.pdf` ends as **Failed** |
| 10 | Phone layout | Browser dev tools, 390 × 844, chat open |
| 11 | Light and dark | The same screen in the other theme |
| 12 | AWS console (optional) | CloudWatch alarms list, all OK; SQS queues `IngestQueue` and `IngestDLQ` |

## Video (about 2 minutes, no sound needed; add captions afterwards)

| Time | Action | Caption |
|---|---|---|
| 0:00 | Sign-in page, then sign in | "Private workspace: accounts are created by the admin." |
| 0:10 | Drag both PDFs in | "Files go straight to a private S3 bucket. A queue and a worker check and index them." |
| 0:25 | Statuses change to Ready | "No refresh: the list follows the indexing." |
| 0:35 | Ask the English question, open the source | "Answers come only from your documents, with the passage they came from." |
| 0:55 | Ask the Vietnamese question | "English and Vietnamese, in either direction." |
| 1:15 | Ask the Australia question | "If the documents don't say it, the app says so, with no made-up sources." |
| 1:30 | Upload `fake.pdf` | "A renamed text file is rejected and deleted." |
| 1:45 | Delete a document, ask about it again | "Deleting removes it from storage and from the search index." |
| 2:00 | End card with the architecture diagram | "Serverless on AWS: CDK, Cognito, API Gateway, Lambda, SQS, Bedrock Knowledge Bases, S3 Vectors." |

Windows: Win + Alt + R starts and stops a screen recording (Xbox Game Bar). Win + Shift + S takes a screenshot.

## After recording

`scripts\destroy.ps1 -Force`. The teardown check must pass. Then add the screenshots and a link to the video in `README.md`.
