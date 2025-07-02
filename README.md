# Digest

A tool for extracting the signal from the noise.

## Overview

Digest fetches data from configured sources, assembles prompts based on my interests and criteria, and uses an LLM to evaluate the relevance and importance of each item. It's designed to help me find the "needles in the haystack" - the rare few things that are truly relevant to my interests.

## Features

- [x] Easily add multiple data sources with their own configuration
  - [x] Start with a simple base configuration and refine with source-specific prompts
  - [ ] Allow all parameters to be customized per-source
- [x] Use any LLM through Ollama to evaluate content against your criteria
  - [x] Extract summaries, evaluations, and confidence scores
- [x] See all results in a simple web view
  - [x] Get it all wrapped up in a weekly email digest
- [x] Advanced data handling
  - [x] Run single loaders at a time
  - [x] Gracefully handle data loader failures
  - [x] Cache the data to avoid unnecessary API calls
- [x] Run the evaluation many times and take a weighted average
  - [x] Get smarter about when to re-evaluate items
- [ ] Benchmark different models, prompts, and tools
  - [ ] Easily create a standardized benchmarking set with real inputs and user scores
  - [ ] Evaluate workflows against accuracy (false positive/negative), inference speed, summarization quality
  - [ ] Try: Local models (gemma, mistral, deepseek, qwen, phi)
  - [ ] Try: Provider models (gemini, openai, claude) (batch mode?)
  - [ ] Try: Prompt engineering (red/blue teaming)
- [ ] Get additional data for the model
  - [ ] During collect, fetch links for e.g. HN and RSS
  - [ ] Save images and submit to the model for e.g. ProductHunt and marketing emails
  - [ ] Let the LLM do independent research with e.g. Perplexity
- [ ] Find better ways to determine how important/interesting an item is
  - [ ] Build personas looking for different things and let each give its own score
  - [ ] Have the LLM compare multiple items to build a ranked list
  - [ ] Give it a feedback loop to learn (maybe with Reddit-style upvotes/downvotes)

## Data Sources

- [x] [Manifund Projects](https://manifund.org/)
- [x] [FreshRSS Unread Items](https://github.com/FreshRSS/FreshRSS)
- [ ] [Manifold Markets](https://manifold.markets)
- [x] Manifold Comments
- [x] [Arxiv Papers](https://arxiv.org/)
- [ ] [Kickstarter Projects](https://www.kickstarter.com/)
- [x] [ProductHunt](https://www.producthunt.com/)
- [ ] [Reddit Posts](https://old.reddit.com)
- [ ] Discord Conversations
- [ ] Twitter Conversations
- [ ] Email Inbox
- [ ] Raw RSS Feed
- [ ] GitHub Home Feed
- [ ] GitHub Repository
- [ ] YouTube Recommendations
- [ ] Google Calendar Events
- [ ] Weather Forecast

## Requirements

- UV package manager
- Just command runner (recommended)
- Ollama running locally or accessible via network

## Installation & Usage

1. Clone or download this project
2. Install dependencies & set up environment variables:
   ```bash
   just init
   ```
3. Edit your prompts to taste:
   ```bash
   nano sources/base.toml
   nano sources/arxiv/config.toml
   ```
4. Run the full workflow:
   ```bash
   just workflow
   ```

### Advanced Usage

```bash
# Step 1: Collect data from all sources
just collect

# Collect data from a specific source only
just collect-one arxiv

# Step 2: Evaluate collected data with LLM
just evaluate

# Evaluate indefinitely
just evaluate-forever
```

### Viewing Results

After running the digest, you can view the results in a simple web interface:

```bash
just web
```

Then generate and send an HTML email digest of filtered results:

```bash
# Preview the digest
just email-preview

# Send email via Mailgun
just email-send
```

## Two-Step Workflow

Digest now uses a two-step workflow for better efficiency and reliability:

### Step 1: Data Collection (`just collect`)

- Runs all configured data loaders
- Collects raw data from sources
- Merges with existing data, preserving evaluations
- Saves to `raw_data.json`

### Step 2: Evaluation (`just evaluate`)

- Loads collected data from `raw_data.json`
- Identifies items needing LLM evaluation
- Assembles prompts and calls Ollama
- Saves final results to `digest_results.json`

## Configuration

### Environment Variables

Secrets and data loaders configuration variables are stored in environment variables. These are automatically loaded when found in `.env`. The required items can be found in `.env.example`, which can be used as a template.

### Base Configuration

The base configuration is in `sources/base.toml` and contains:

- **header**: Your interests and preferences
- **introduction**: Task introduction
- **container_pre/post**: Tags to isolate input content
- **criteria**: Evaluation criteria
- **instructions**: Output format instructions

## Source Configuration

Each source has its own directory under `sources/` with the following items.

### Configuration File

The configuration file for each source must be named `config.toml`.

The only required key is `loader`, which must point to an executable data loader, described below.

Optionally, you can overwrite any of the prompt segments defined in the base configuration by using the same keys.

### Data Loader

Data loaders must:
1. Be executable scripts
2. Output valid JSON to stdout
3. Return a list of items, each with at least:
   ```json
   {
     "source": "Source Name",
     "title": "Item Title",
     "link": "https://example.com/item",
     "creation_date": "2024-13-32T19:16:33+00:00",
     "input": { ... actual content to evaluate ... }
   }
   ```
