# Exam Generator — Help Guide

A practical, screen-reader-friendly guide to creating and taking exams with the
Exam Generator. This guide matches the exam-generator skill and has been checked
against the live exam page, so every feature listed here actually exists.

## How to provide content
You can get an exam two ways:
- **Ask for a topic.** For example: "Make me a 5-question quiz on the water cycle."
- **Drop in your own material.** Put source files (notes, PDFs, docs) into the
  `plugins/exam_application/content/` folder and ask the agent to build an exam
  from them. Files in that folder are treated as private and read through the
  local privacy broker, so their contents are not sent to the cloud.

## Supported question types
- **Multiple choice** — one correct option. (A "true/false" question is just a
  multiple-choice question with two options — it is not a separate type.)
- **Select all that apply** (multi-select) — one or more correct options.
- **Fill in the blank** — type the missing word or phrase.
- **Dropdown** — choose the missing word from a list.
- **Matching** — match items in one column to the other.
- **Terminal command** — type the correct command.

## Features the exam supports
- **Timers** — an optional countdown for the whole exam.
- **Anti-cheat mode** — optional; flags leaving the exam tab/window.
- **Weighted scoring** — questions can be worth different amounts.
- **Partial credit** — partial marks on multi-answer questions.
- **Answer explanations** — every question can include an explanation so you
  learn the moment you answer.
- **Embedded media** — an image, audio clip, or video can appear above a
  question, with descriptive alt text for screen readers.

## Not available (so you know what to expect)
These are **not** part of the exam app today:
- **Retake or resume** — there is no saving of progress or reopening a past
  exam in place. (Ask for a new exam to try again — it builds a fresh one.)
- **Changing colours or text size during a test** — the exam has no in-test
  colour or font-size controls. Asking for changes mid-exam rebuilds the exam
  rather than restyling the one you are taking.
- **A one-exam-at-a-time limit** — there is no such rule.

## Keyboard shortcuts & navigation
- **Alt+N** — submit your answer / go to the next question.
- **Alt+T** — announce the time remaining.
- **Alt+H** — open the global Help menu.
- **H (heading key)** — jump between headings: the exam title (H1) and the
  current question (H2). To skip past an embedded video or audio, press **H** to
  jump straight to the "Question Prompt" and "Answer Options" landmarks (H3).

## Example prompts
- **Basic:** "Generate a quick 3-question multiple-choice quiz on JavaScript arrays."
- **Intermediate:** "Read the PDF in the content folder and build a 5-question
  exam using dropdowns and fill-in-the-blanks."
- **Complex:** "Create a 10-minute weighted exam on Linux commands. Include 2
  terminal-command questions, 2 matching columns, and embed a relevant tutorial
  video on question 3."

## Build one now
When this guide is shown in chat, the Exam Builder is embedded at the end:

```html
<iframe src="/plugin/exam_builder" class="w-full min-h-[600px] border-0 rounded-lg shadow-xl" allow="autoplay; encrypted-media; fullscreen; picture-in-picture" allowfullscreen title="Exam Generator Builder"></iframe>
```
