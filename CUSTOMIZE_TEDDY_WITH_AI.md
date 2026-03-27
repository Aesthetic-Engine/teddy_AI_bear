# Customize Teddy With AI

Use this file with Cursor, Claude Code, Codex, or another coding agent to help customize Teddy for a new owner and machine.

## Purpose

The assistant should ask the user a short series of practical questions, then write the answers into the appropriate Teddy files.

The goal is to make Teddy feel personal without requiring the user to hunt through the repo manually.

## Files The Assistant May Update

- `workspace/USER.md`
- `workspace/TOOLS.md`
- `workspace/MEMORY.md`

Only update `workspace/SOUL.md` or `workspace/IDENTITY.md` if the user explicitly asks for deeper personality changes.

## How The Assistant Should Work

1. Read `README.md` first for repo context.
2. Read the current files in `workspace/` before making changes.
3. Ask questions in small batches instead of one giant form.
4. Prefer concrete, practical questions over abstract personality talk.
5. After the user answers, update the appropriate files directly.
6. Summarize what was changed and where it was written.

## Question Flow

The assistant should gather information in this order.

### 1. Owner Identity

Ask:

- What is your name?
- What should Teddy call you?
- What pronouns should Teddy know, if any?
- What timezone should Teddy assume?

Write to:

- `workspace/USER.md`

### 2. How Teddy Should Help

Ask:

- What kind of help do you want most from Teddy?
- Do you want Teddy to be more practical, more companion-like, or balanced?
- Are there any tones or behaviors Teddy should avoid?

Write durable, high-level preferences to:

- `workspace/USER.md`
- `workspace/MEMORY.md`

Do not overstuff these files. Keep the notes short and durable.

### 3. Local Machine And Hardware

Ask:

- What microphone should Teddy use?
- What speaker or output device should Teddy use?
- What serial port is the mouth controller on?
- Is Teddy using the Arduino Nano plus PCA9685 mouth setup?
- Is the mouth enabled right now?

Write to:

- `workspace/TOOLS.md`

### 4. Voice And Runtime Preferences

Ask:

- Which Piper voice should Teddy use?
- Are you using a standard Piper voice or a Mantella Fallout 4 voice?
- Do you want wake-word mode enabled by default?
- Do you want Teddy to auto-listen on startup?

Write environment-facing notes and preferred local setup values to:

- `workspace/TOOLS.md`

### 5. Durable Personal Context

Ask only for things that should actually help Teddy feel personal over time, such as:

- important communication preferences
- long-term projects
- stable interests
- meaningful relationship context
- things Teddy should remember not to assume

Write concise durable notes to:

- `workspace/MEMORY.md`

Do not write private secrets, financial details, passwords, or one-off temporary chatter.

## Editing Rules

- Keep `workspace/USER.md` focused on the human.
- Keep `workspace/TOOLS.md` focused on machine setup, hardware, paths, and devices.
- Keep `workspace/MEMORY.md` focused on durable truths and recurring context.
- Do not turn the workspace files into long biographies.
- Prefer boring, explicit wording over poetic filler when writing setup facts.

## Example Prompt For A Coding Agent

You can give an AI assistant this instruction:

> Read `CUSTOMIZE_TEDDY_WITH_AI.md`, then customize Teddy for me by asking me the questions in small batches and writing my answers into the correct files.

## Expected Outcome

After this process:

- Teddy knows what to call the user
- Teddy has machine-specific hardware and audio notes
- Teddy has a small amount of durable personal context
- the repo remains clean and understandable
