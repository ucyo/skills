---
name: concise-readme
description: Generate a concise, well-structured README for Docker images, CLI tools, or libraries. Creates minimal documentation focused on quick-start usage.
---

# Concise README Generator

Generates a minimal, user-focused README following a proven structure.

## Structure

The README should follow this pattern:

1. **Title and Introduction** - Single paragraph describing the project, key features, and automated processes
2. **Getting Started** - Practical usage examples grouped together

## Guidelines

### First Paragraph
- Start with a one-sentence description
- Include important details: platforms supported, auto-update behavior, key features
- Make it flow naturally as 1-2 sentences maximum
- Avoid bullet points in the intro

### Getting Started Section
- Group all usage examples under one "Getting Started" heading
- Use bold labels before code blocks: `**Pull and run:**`, `**Build locally:**`, `**Install:**`
- Show the most common use case first
- Keep examples minimal and copy-paste ready
- No explanations needed if the code is self-evident

## What to Avoid
- Long feature lists
- "What's Included" sections (fold into intro if critical)
- Multiple H2 sections for simple projects
- Separate "Installation", "Usage", "Build" sections (combine them)
- Tag lists (remove or make inline)
- Platform/architecture details in separate sections (put in intro)

## Example Output

```markdown
# Project Name

Brief description with key features and automated processes. Platform support and other critical info in natural prose.

## Getting Started

- **Pull and run:**
    \`\`\`bash
    docker pull user/image:latest
    docker run --rm -it user/image:latest
    \`\`\`

- **Build locally:**
    \`\`\`bash
    make build
    make run
    \`\`\`

## Usage

When asked to create or update a README:
1. Read existing files to understand the project
2. Identify the project type (Docker image, CLI tool, library)
3. Extract key information: features, platforms, automation, usage
4. Generate README following the structure above
5. Keep it under 20 lines total
6. Focus on getting users started quickly
