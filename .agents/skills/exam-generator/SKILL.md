---
name: exam-generator
description: Generates highly accessible, dynamic exams and quizzes from user-provided content. Supports multiple question types, media embeds, and timers.
---

# Exam Generator Skill

## Overview
When the user asks you to generate a quiz, exam, or assessment based on their content, you must use this skill. The Exam Application is a dynamic, highly accessible front-end plugin that reads a specific JSON schema to render multiple-choice, multi-select, fill-in-the-blank, dropdown, matching, and terminal-command questions.

## Workflow
1. **Analyze Content (Raugus Sensitive Vault):** Read the source materials the user has provided. Often, they will drop documents into the `plugins/exam_application/content/` folder.
   - **Privacy Broker Note:** Because `plugins/exam_application/content/` is marked `sensitive: true` in the Raugus Map, any attempt to directly `view_file` or `cat` files inside it will be intercepted by the Raugus Hook, which will automatically return a sanitized **Local Brain Digest** from the local `Qwen2.5-1.5B` model.
   - **Conversing with the Local Brain:** To extract specific exam questions or ask follow-up questions about files in `plugins/exam_application/content/` without exposing raw PII to the cloud, run:
     `python3 /mnt/c/Users/michael/Documents/DevCore/security/local_brain_broker.py --target "/mnt/c/Users/michael/Documents/DevCore/plugins/exam_application/content" --mode exam --count 5 --query "Your specific question types and topic instructions"`
     (or `--mode query --query "Your follow-up question"`).
2. **Generate JSON:** Formulate questions, plausible distractors, and **detailed educational explanations** for every answer based strictly on the source content or the Local Brain Broker's sanitized output.
3. **Save Data:** Write the resulting JSON payload to `sandbox/static/exam_temp.json`.
4. **Format & Validate:** You MUST execute the included schema normalizer script to fix any subagent hallucinations before rendering the UI:
   `python3 /mnt/c/Users/michael/Documents/DevCore/.agents/skills/exam-generator/scripts/format_exam.py /mnt/c/Users/michael/Documents/DevCore/sandbox/static/exam_temp.json`
5. **Activate UI:** Embed the plugin directly into your chat response by rendering an iframe:
   ```html
   <iframe src="/plugin/exam?quiz=exam_temp.json&title=Your+Custom+Title" class="w-full aspect-video border-0 rounded-lg" allow="autoplay; encrypted-media; fullscreen; picture-in-picture" allowfullscreen></iframe>
   ```

## Blueprint & JSON Templating
The Exam Application UI is a read-only blueprint. To automate and extend the application (e.g., adding a timer, enabling partial credit, or adding textboxes), you must modify the JSON payload. 
- Treat the JSON schema as your ultimate configuration template.
- Do not attempt to write HTML or broken JS from scratch to add features.
- If a user requests a complex UI behavior, generate a comprehensive JSON payload that leverages the supported schema features to achieve the result.

## JSON Schema Specification
**CRITICAL RULES FOR SUBAGENTS:**
- NEVER use the key `"question"` for the question text. You MUST use exactly `"text"`.
- For `multiple_choice` questions, NEVER use `"correct_answer"` with a string. You MUST use `"correct_index"` with an **integer** representing the 0-based index of the correct option in the `"options"` array.
- For `multi_select` questions, NEVER use `"correct_answers"` with an array of strings. You MUST use `"correct_indices"` with an array of **integers** representing the 0-based indices.
- For `dropdown_blank`, you MUST only have exactly one `[BLANK]` string in the `"text"` field. Do NOT create nested dictionaries for multiple blanks. Use `"correct_text"` for the single correct string.

The plugin expects a root object containing an optional `timer_seconds`, optional `weighted_scoring` (boolean), optional `partial_credit` (boolean), optional `anti_cheat` (boolean), and a `questions` array.

```json
{
  "timer_seconds": 600, 
  "weighted_scoring": true,
  "partial_credit": true,
  "anti_cheat": true,
  "questions": [
    {
      "type": "multiple_choice",
      "text": "What is the primary function of a mitochondria?",
      "weight": 2.5,
      "options": ["Energy production", "Protein synthesis", "Waste disposal"],
      "correct_index": 0,
      "explanation": "The mitochondria is the powerhouse of the cell..."
    },
    {
      "type": "multi_select",
      "text": "Which of the following are valid HTTP methods? (Select all that apply)",
      "weight": 3.0,
      "options": ["GET", "FETCH", "POST", "PUSH"],
      "correct_indices": [0, 2],
      "explanation": "GET and POST are valid HTTP methods. FETCH and PUSH are not standard methods."
    },
    {
      "type": "text_response",
      "text": "Type the missing word: The sky appears [blank] due to Rayleigh scattering.",
      "correct_text": "blue",
      "explanation": "Rayleigh scattering deflects short-wavelength light (blue)..."
    },
    {
      "type": "dropdown_blank",
      "text": "The primary ingredient in hummus is [BLANK].",
      "options": ["chickpeas", "lentils", "black beans"],
      "correct_text": "chickpeas",
      "explanation": "Hummus is traditionally made from mashed chickpeas."
    },
    {
      "type": "match_columns",
      "text": "Match the programming language to its primary paradigm.",
      "pairs": [
        {"left": "Haskell", "right": "Functional"},
        {"left": "Java", "right": "Object-Oriented"},
        {"left": "C", "right": "Procedural"}
      ],
      "explanation": "Different languages favor different structural paradigms."
    },
    {
      "type": "terminal_command",
      "text": "What command would you use to list all files, including hidden ones, in a directory?",
      "correct_command": "ls -a",
      "explanation": "The 'ls' command lists directory contents, and the '-a' (all) flag includes hidden files."
    }
  ]
}
```

### Media Integration (Optional)
Any question object can include a `media` field to render images, audio, or video above the question text.
```json
"media": {
  "type": "video", 
  "url": "/plugin/media?v=video_id_here&minimal=true",
  "alt": "Description of the visual content for screen readers"
}
```
*Note: `type` can be `"video"`, `"audio"`, or `"image"`. The `url` should be the relative or absolute path to the asset. For videos, ALWAYS append `&minimal=true` to hide the standalone player's playlist UI.*

## Accessibility Requirements
- Do not use markdown inside the `text` or `explanation` fields. Use raw text or extremely simple HTML entities if necessary.
- Ensure all `alt` text for media is highly descriptive.
- Always provide a robust `explanation` for every question so users can learn from their mistakes immediately.


## Handling Specific "Help Exam Generator" Requests
When the user specifically asks for help with the Exam Generator (e.g., by clicking the "help exam generator" button or typing that exact phrase), you must provide a comprehensive, screen-reader-friendly user guide. 

*Do NOT dump these specific details into the main, high-level "Help Menu" if the user only typed "help" or pressed `Alt+H`. Keep the global Help Menu strictly to high-level overviews and buttons.*

**Your detailed Exam Generator guide must include:**
1. **How to Provide Content:** Explain that the user can ask you to generate an exam based on a topic, or they can drop source documents directly into the `plugins/exam_application/content/` folder for you to read.
2. **Supported Question Types:** List that you can generate Multiple Choice, Fill-in-the-blank, Dropdown, Matching, and Terminal Command questions.
3. **Features:** Mention that exams support customizable timers, weighted scoring, partial credit, detailed educational explanations for answers, and embedded media (audio, video, images).
4. **Keyboard Shortcuts & Navigation:**
   - **Alt+N**: Submit answer / Go to Next question.
   - **Alt+T**: Announce the remaining time on the exam.
   - **Alt+H**: Open the global Help menu.
   - **Heading Navigation ('H' Key)**: Use 'H' to jump between the Exam Title (`H1`) and Current Question (`H2`).
   - **Media Bypass (New Feature)**: To quickly skip past video/audio embeds, press 'H' to jump directly to the hidden **"Question Prompt"** (`H3`) and **"Answer Options"** (`H3`) landmarks.
5. **Example Prompts:** Provide the user with a few practical examples of how to ask for exams, ranging from basic to complex. For example:
   - *Basic:* "Generate a quick 3-question multiple-choice quiz on JavaScript arrays."
   - *Intermediate:* "Read the PDF in the content folder and build a 5-question exam using dropdowns and fill-in-the-blanks."
   - *Complex:* "Create a 10-minute weighted exam on Linux commands. Include 2 terminal-command questions, 2 matching columns, and embed a relevant tutorial video on question 3."
6. **Interactive Generation UI:** ALWAYS embed the Exam Builder UI at the end of the guide using the following iframe: `<iframe src="/plugin/exam_builder" class="w-full min-h-[600px] border-0 rounded-lg shadow-xl" allow="autoplay; encrypted-media; fullscreen; picture-in-picture" allowfullscreen title="Exam Generator Builder"></iframe>`

Format the guide using clean Markdown headers and bullet points. Keep it practical and focused on how the user can interact with the app.
