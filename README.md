# Study Buddy

![Study Buddy MCP Server banner](assets/banner.png)

> Turn your notes and past papers into a focused, local AI study system.

**Study Buddy** is a Python MCP server that gives an MCP client such as Claude structured access to your study material.

Drop notes, slides, textbook extracts, and previous-year question papers into local folders. Study Buddy can search and read them, discover topics, teach concepts in different styles, create grounded quizzes, analyse PYQ patterns, and track your progress over time.

The project is also designed as a practical way to learn **MCP, the Model Context Protocol**. It demonstrates how tools, resources, prompts, typed inputs, local state, and safe file access fit together in a real server.

---

## What is MCP?

MCP is a standard that lets AI applications connect to external tools, data, and workflows.

In this project:

- **MCP client**: the AI application that connects to and uses Study Buddy.
- **MCP server**: this Python application, `study_buddy.py`.
- **Tools**: actions the client can call, such as searching notes or logging a quiz score.
- **Resources**: browsable context exposed by the server, such as available content files or a mastery tracker.
- **Prompts**: reusable study workflows, such as studying a topic, taking a quiz, or practising with PYQs.
- **Persistent state**: information that survives across sessions. Study Buddy uses SQLite to keep track of topics and quiz results.

---

## Features

### Study material management

- Separate folders for notes and previous-year question papers
- Supports `.txt`, `.md`, `.pdf`, `.docx`, `.png`, `.jpg`, `.jpeg`, and `.webp`
- Lists available content and PYQ files
- Reads individual files safely
- Searches across study content
- Archives files you no longer want in active use

### Topic and progress tracking

- Discovers possible study topics from headings, bold text, and common exam-question wording
- Registers topics for tracking
- Logs quiz results in a local SQLite database
- Calculates mastery percentage across attempts
- Shows your weakest active topics
- Lets you archive mastered topics

### Previous-year question paper support

- Extracts questions from past papers
- Analyses question count, question types, marks distribution, and common question stems
- Supports practice with real PYQ questions
- Supports creating new questions that match a paper’s style while staying grounded in your notes

### MCP primitives

- **Tools** for actions such as searching files, logging results, and analysing PYQs
- **Resources** for browsable study context
- **Prompts** for reusable study workflows
- Typed inputs and descriptions using Pydantic fields
- Safe local-file boundaries to prevent access outside approved folders

---

## Project structure

```text
study-buddy/
├── assets/
│   └── banner.png
├── materials/
│   ├── archive/
│   ├── content/
│   │   ├── notes.md
│   │   ├── chapter-1.pdf
│   │   └── slides.docx
│   └── pyqs/
│       ├── midterm-2024.pdf
│       └── final-2023.txt
├── study_buddy.py
├── study.db
├── pyproject.toml
├── uv.lock
├── .gitignore
└── README.md
```

`study.db` is created automatically when the server runs for the first time.

---

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- An MCP-compatible client, such as Claude Desktop
- Node.js is helpful for launching the MCP Inspector through the MCP CLI

The project uses:

- `mcp`
- `pypdf`
- `python-docx`

---

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/<your-username>/study-buddy-mcp.git
cd study-buddy-mcp
```

### 2. Install dependencies

```bash
uv sync
```

This creates a virtual environment and installs everything listed in `pyproject.toml`.

### 3. Add your study material

Place your normal course material inside:

```text
materials/content/
```

Examples:

```text
materials/content/
├── dbms-notes.md
├── transactions.pdf
├── normalization-slides.docx
└── er-diagram.png
```

Place previous-year question papers inside:

```text
materials/pyqs/
```

Examples:

```text
materials/pyqs/
├── dbms-midterm-2024.pdf
├── dbms-final-2023.txt
└── operating-systems-pyq.docx
```

Use `materials/archive/` for files you no longer want included in active study workflows.

---

## Run and test the server

Use the MCP Inspector during development:

```bash
uv run mcp dev study_buddy.py
```

The first run may ask permission to download and launch the Inspector through `npx`.

Once the Inspector opens, you can inspect and call:

- tools
- resources
- prompts
- input schemas
- responses and errors

This is the easiest way to verify that each MCP capability works before connecting the server to an AI client.

---

## Connect it to an MCP client

Study Buddy runs as a local stdio MCP server.

When adding it to an MCP-compatible client, configure the client to run:

```text
Command: uv
Arguments: run study_buddy.py
Working directory: /absolute/path/to/study-buddy
```

The exact configuration screen differs between MCP clients, but the server entry should point to the project directory and run `uv run study_buddy.py`.

---

## Available tools

### Material tools

| Tool | What it does |
| --- | --- |
| `list_content` | Lists files inside `materials/content/` |
| `list_pyqs` | Lists files inside `materials/pyqs/` |
| `read_file` | Reads a file from `content`, `pyqs`, or `archive` |
| `search_content` | Searches across content files for a word or phrase |
| `archive_files` | Moves selected content or PYQ files into `materials/archive/` |

### Topic and progress tools

| Tool | What it does |
| --- | --- |
| `discover_topics` | Finds likely topics from material headings, bold text, and question wording |
| `register_topic` | Adds a topic to the progress tracker |
| `list_topics` | Shows active topics, attempts, mastery, and last attempt |
| `archive_topic` | Marks a topic as mastered and hides it from active tracking |
| `log_result` | Saves a quiz or test score |
| `weakest_topics` | Returns the active topics with the lowest mastery |

### PYQ tools

| Tool | What it does |
| --- | --- |
| `extract_pyq_style` | Analyses a past paper’s structure and question patterns |
| `extract_pyq_questions` | Extracts parsed questions from a past paper |

---

## Available resources

| Resource | What it contains |
| --- | --- |
| `study://content` | Index of files in `materials/content/` |
| `study://pyqs` | Index of files in `materials/pyqs/` |
| `study://topics` | Current active and archived topic mastery tracker |

Resources are useful when a client needs to browse server context rather than perform a one-off action.

---

## Available prompts

### Study a topic

Teaches a topic from your own uploaded content.

Example:

```text
Study normalization using the Feynman style.
```

Possible styles include:

```text
default
feynman
socratic
eli5
5 bullet summary
exam-cram
interview-style
```

### Quiz me on a topic

Creates a quiz grounded only in relevant material from `materials/content/`.

Example:

```text
Quiz me on functional dependencies with 5 questions.
```

The quiz is delivered one question at a time, feedback is given after every answer, and the final result is saved to the tracker.

### PYQ test

Practises a topic using either real past-paper questions or fresh questions written in a matching PYQ style.

Example:

```text
Give me a PYQ-style test on normalization with 5 questions.
```

---

## How Study Buddy keeps file access safe

The server only allows file operations inside these folders:

```text
materials/content/
materials/pyqs/
materials/archive/
```

It validates both the folder name and resolved file path before reading or moving a file.

This prevents requests from escaping the project’s study-material boundary and accessing unrelated local files.

---

## Notes on supported files

### Text-based files

These files can be read and searched directly:

```text
.txt
.md
.pdf
.docx
```

### Images

These files are returned as image content for MCP clients that support vision:

```text
.png
.jpg
.jpeg
.webp
```

### Scanned PDFs

A scanned PDF may not contain selectable text, so `pypdf` may return little or no extractable content.

For scanned notes, consider adding a text-based version or using OCR before placing them in `materials/content/`.

---

## Example workflow

A typical Study Buddy session can look like this:

```text
1. List my content files.
2. Discover topics from my material.
3. Register normalization and functional dependencies.
4. Teach me normalization in an exam-cram style.
5. Quiz me on normalization with 5 questions.
6. Show my weakest topics.
7. Give me a PYQ-style test on functional dependencies.
```

Behind the scenes, the MCP client can combine tools, resources, and prompts to create a focused study workflow from your own material.

---

## Extending the project

Study Buddy is intentionally built around reusable MCP ideas.

You can adapt the same structure into:

- a research-paper assistant
- a local documentation navigator
- a codebase explainer
- a job-application tracker
- a personal finance coach
- a recipe and meal-planning assistant
- a language-learning companion

The domain can change. The MCP building blocks stay the same:

```text
safe data access
+ useful tools
+ browsable resources
+ reusable prompts
+ persistent state
= a practical MCP server
```

---

## Built with

- Python
- FastMCP
- SQLite
- Pydantic
- pypdf
- python-docx
- uv

---

## License

This project is licensed under the [MIT License](LICENSE).