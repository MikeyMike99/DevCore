---
name: exam-generator
description: Create exams and quizzes. Everything needed is in this file - write the exam JSON yourself and emit it in a [SAVE_EXAM] block; do not read other files, plugins or scripts.
---

# Exam Generator

## The whole workflow (no other files needed)
1. **Do not inspect anything.** Do not open project files, the exam plugin, the content folder, other skills or scripts, and do not run commands. This file is the complete specification.
2. **Write the questions yourself.** If the user attached material, it appears inside `<ATTACHED_DOCUMENT>` tags in their message; base the questions strictly on it. Otherwise use your own knowledge of the topic. Honour the requested number of questions, question types, timer and difficulty.
3. **Reply with one short sentence, then the exam JSON in a `[SAVE_EXAM]` block:**
   ```
   Here is your 5-question quiz on photosynthesis.
   [SAVE_EXAM]
   {"title": "Photosynthesis Basics", "timer_seconds": 300, "questions": [ ... ]}
   [/SAVE_EXAM]
   ```
4. **That's it.** The system validates the JSON, saves it under its own name and shows the user a link plus the embedded exam. Do not write files, iframes or links yourself, and never edit the exam HTML.

## JSON format
Root object: `title` (string), optional `timer_seconds` (int), optional `weighted_scoring` (bool), optional `partial_credit` (bool), optional `anti_cheat` (bool), and a `questions` array.

Every question has `type`, `text`, an `explanation` (plain text, no markdown) and an optional `weight` (number).

**Strict rules:**
- The question text key is `text`, never `question`.
- `multiple_choice` uses `correct_index` (0-based integer), never `correct_answer`.
- `multi_select` uses `correct_indices` (array of 0-based integers), never `correct_answers`.
- `dropdown_blank` has exactly one `[BLANK]` in `text` and uses `correct_text`.

```json
{
  "title": "Sample Exam",
  "timer_seconds": 600,
  "weighted_scoring": true,
  "partial_credit": true,
  "questions": [
    {"type": "multiple_choice", "text": "What is the primary function of mitochondria?", "weight": 2,
     "options": ["Energy production", "Protein synthesis", "Waste disposal"], "correct_index": 0,
     "explanation": "Mitochondria produce ATP, the cell's main energy source."},
    {"type": "multi_select", "text": "Which are valid HTTP methods? (Select all that apply)",
     "options": ["GET", "FETCH", "POST", "PUSH"], "correct_indices": [0, 2],
     "explanation": "GET and POST are standard HTTP methods; FETCH and PUSH are not."},
    {"type": "text_response", "text": "The sky appears which colour due to Rayleigh scattering?",
     "correct_text": "blue", "explanation": "Rayleigh scattering deflects short-wavelength blue light the most."},
    {"type": "dropdown_blank", "text": "The primary ingredient in hummus is [BLANK].",
     "options": ["chickpeas", "lentils", "black beans"], "correct_text": "chickpeas",
     "explanation": "Hummus is traditionally made from mashed chickpeas."},
    {"type": "match_columns", "text": "Match the language to its primary paradigm.",
     "pairs": [{"left": "Haskell", "right": "Functional"}, {"left": "Java", "right": "Object-Oriented"}, {"left": "C", "right": "Procedural"}],
     "explanation": "Different languages favour different paradigms."},
    {"type": "terminal_command", "text": "Which command lists all files, including hidden ones?",
     "correct_command": "ls -a", "explanation": "ls lists directory contents; -a includes hidden files."}
  ]
}
```

### Optional media
Any question may include `"media": {"type": "video" | "audio" | "image", "url": "...", "alt": "descriptive text for screen readers"}`. For videos use `/plugin/media?v=<id>&minimal=true`.

## Accessibility
- No markdown inside `text` or `explanation`.
- Always give a helpful `explanation` so users learn from mistakes.
- Media `alt` text must be descriptive.

## "Help exam generator" requests
Only when the user asks for help with the Exam Generator itself (not when they ask for an exam): present the guide in `plugins/exam_application/HELP_GUIDE.md` and end with
`<iframe src="/plugin/exam_builder" class="w-full min-h-[600px] border-0 rounded-lg shadow-xl" title="Exam Generator Builder"></iframe>`.
Keep this out of the general Help menu (Alt+H).
