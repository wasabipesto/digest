# Digest

A tool for extracting the signal from the noise.

## Overview

Digest fetches data from configured sources, assembles prompts based on my interests and criteria, and uses an LLM to evaluate the relevance and importance of each item. It's designed to help me find the "needles in the haystack" - the rare few things that are truly relevant to my interests.

## Features

- [x] Easily add multiple data sources with their own configuration
- [x] Start with a simple base configuration and refine with source-specific prompts
- [x] Use any LLM through Ollama to evaluate content against your criteria
- [x] Extract summaries, evaluations, and confidence scores
- [ ] Cache the data to avoid unnecessary API calls
- [ ] Get it all wrapped up in a weekly email digest
- [ ] Run the evaluation many times and take a weighted average
- [ ] Have the LLM compare multiple items to build a ranked list
- [ ] Enable image interpretation
- [ ] Benchmark the results
- [ ] Let the LLM do research on its own with Perplexity
- [ ] Build personas looking for different things and let each give its own score
- [ ] Give it a feedback loop to learn (maybe with Reddit-style upvotes/downvotes)

## Data Sources

- [x] [Manifund Projects](https://manifund.org/)
- [ ] FreshRSS Unread
- [ ] Kickstarter Projects
- [ ] ProductHunt
- [ ] Manifold Markets
- [ ] Reddit Posts
- [ ] Discord Conversations
- [ ] Twitter Conversations
- [ ] Arxiv Papers
- [ ] Email Inbox
- [ ] Raw RSS Feed
- [ ] GitHub Home Feed
- [ ] GitHub Repository
- [ ] YouTube Recommendations
- [ ] Google Calendar Events
- [ ] Weather Forecast

## Requirements

- UV package manager
- Ollama running locally or accessible via network

## Installation

1. Clone or download this project
2. Install dependencies:
   ```bash
   uv sync
   ```

## Configuration

### Environment Variables

This file should be located at `.env`.

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

Then configuration file for each source must be named `config.toml`.

The only required key is `loader`, which must point to an executable data loader, described below.

Optionally, you can overwrite any of the prompt segments defined in the base configuration

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
     "input": { ... actual content to evaluate ... }
   }
   ```

## Usage

```bash
just run # convenience runner
uv run main.py # run manually
```
