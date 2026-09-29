# Working on English Class

Read README.md, docs/DESIGN.md, docs/API.md and docs/TEST_REPORT.md first.

Run `bash scripts/test_all.sh` from the repo root using Python 3.11+, test requirements, Node.js and ffmpeg. Write a failing regression before a behavior fix. Provider substitutes must remain under tests/; never silently switch production to mock answers.

Do not overwrite or stop existing aibot production automatically. This extension installs separately. Only an explicit course_mode switch controls the original microphone service. Do not push or deploy without the user's request.

Use only original WordMaster dictionary data; positive unit means ordered practice group, not textbook unit. Keep original IDs, meanings and grade/semester. No provider secrets in student directories or mini-program.

Keep separate student process state and credential checks. A request student_id is not authentication. Parent credential cannot write progress or call provider routes. Do not publish /internal/.

An unclear recognition must not downgrade state. Echoed answers must not count as independent speech. ASR transcription is not a pronunciation score. UI must distinguish request failure from empty results.

New API fields require synchronized updates to documentation, mini-program, brain, tests and deployment instructions. Do not claim hardware/WeChat/provider verification from localhost mocks.
