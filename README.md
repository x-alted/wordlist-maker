# Wordlist Maker

A flexible password/wordlist generator for cybersecurity training, CTFs, and penetration testing.
It creates password variations from personal facts, company info, or any topic – with optional web scraping and smart date‑based password generation.

## Features

- **Interactive or CLI mode** – choose your preferred workflow.
- **Single or multiple phrases** – combine them with separators, in all orders.
- **Case mutations** – original, lower, upper, title, swapcase, and random case.
- **Number & special character suffixes** – configurable lists (e.g., `123`, `!`, `2024`).
- **Exhaustive mode** – generate *every* possible combination (deterministic, no randomness).
- **Streaming mode** – write directly to disk with minimal memory usage, ideal for huge wordlists.
- **Deduplication** – optional set‑based uniqueness (memory‑intensive).
- **Progress bars** – if `tqdm` is installed.
- **Graceful interrupt handling** – partial files are cleaned up on `Ctrl+C`.
- **Web scraping** – fetch semantically related words from `relatedwords.io` over **HTTPS** and use them as phrases.
- **Date modes** – generate simple date strings (`--date`) or **strong** password‑ready date variants with ordinals, separators, and specials (`--date-strong`).
- **Sample mode** – preview first N lines without writing a file (`--sample`).
- **Interactive improvements** – show current phrases, `back` command to remove last phrase, `list` command.
- **Safe filenames** – long combined filenames are automatically truncated with a hash to avoid OS limits.
- **Deterministic ordering** – default suffix lists and strong date output are reproducible (preserves insertion order).

## Installation

The script requires **Python 3.6+** and no mandatory external libraries.  
For the web scraping feature, install:

```bash
pip3 install requests beautifulsoup4
```

For progress bars (optional):

```bash
pip3 install tqdm
```

## Quick Start

### Interactive Mode

Run without arguments:

```bash
python3 wordlist-maker.py
```

You will be guided through:
- Adding phrases manually or scraping them from a topic.
- Setting combination length, suffixes, and other options.
- Generating wordlists and optionally merging them.

**Interactive commands:**  
`back` – remove the last added phrase  
`list` – show current phrases  
`done` / `n` – finish adding phrases and proceed

### CLI Mode – Basic Examples

Generate 10,000 variations for a single phrase:

```bash
python3 wordlist-maker.py --phrases "Fluffy" --count 10000 --output fluffy.txt
```

Combine two phrases with default separators (``, `_`, `-`, `.`):

```bash
python3 wordlist-maker.py --phrases "cat" "dog" --count 5000 --output pets.txt
```

Use **exhaustive** mode (all case & suffix combinations, no randomness):

```bash
python3 wordlist-maker.py --phrases "admin" --exhaustive --output admin_all.txt
```

### Scraping Related Words

Fetch 30 related terms for “football” and merge them with a manual phrase:

```bash
python3 wordlist-maker.py --scrape football --scrape-limit 30 --phrases "goal" --output football_words.txt
```

Scrape multiple topics at once (the tool adds a 0.5s delay between requests):

```bash
python3 wordlist-maker.py --scrape cars gaming music --scrape-limit 20 --output hobbies.txt
```

## Date Modes

### Simple Date Variations (`--date`)

Generate common date representations (e.g., `100914`, `10Sep14`, `September10`, `20140910`).  
By default they are added as **phrases** (so they can be combined with other words). Use `--date-as-suffix` to append them as suffixes.

```bash
# Generate a wordlist with only date strings
python3 wordlist-maker.py --date 15/8/2021 --output date_only.txt

# Append date variations to a base phrase
python3 wordlist-maker.py --phrases "password" --date 15/8/2021 --date-as-suffix --count 5000 --output password_dates.txt

# Combine date phrases with another word
python3 wordlist-maker.py --phrases "welcome" --date 15/8/2021 --max-len 2 --output welcome_dates.txt
```

### Strong Date Passwords (`--date-strong`)

Generate realistic password variants for a date, including:
- Ordinals (`1st`, `2nd`, `3rd`, `4th`, …)
- Month names (full and abbreviated, lower and capitalised)
- Separators (`-`, `/`, `.`, `_`)
- Special characters (`!`, `@`, `#`, `$`, …) placed at beginning, end, or both
- Different orders (day‑month‑year, month‑day‑year, year‑month‑day)

```bash
# Generate strong date passwords directly (as phrases)
python3 wordlist-maker.py --date-strong 10/9/2014 --output strong_dates.txt

# Append strong date variants as suffixes to a base phrase
python3 wordlist-maker.py --phrases "admin" --date-strong 10/9/2014 --date-strong-as-suffix --count 10000 --output admin_strong.txt

# Combine strong date phrases with other terms
python3 wordlist-maker.py --phrases "company" "user" --date-strong 10/9/2014 --max-len 2 --output company_dates.txt

# Preview the first 20 strong date variants without writing a file
python3 wordlist-maker.py --date-strong 10/9/2014 --sample 20
```

**Example output** of `--date-strong 10/9/2014 --sample 5`:

```
september10th2014
10thSeptember2014
2014september10th
10-09-14
10/09/2014!
Sep10th2014?
2014-09-10!!
!10thSeptember2014!
```

## Sample Mode (`--sample`)

Preview the first N lines of generated output without writing a file. Works with any mode (single phrase, combined, exhaustive, date modes).

```bash
# See what a combined wordlist would look like
python3 wordlist-maker.py --phrases "hello" "world" --max-len 2 --sample 10

# Check strong date output
python3 wordlist-maker.py --date-strong 1/1/2020 --sample 8
```

## Command‑Line Options

| Argument | Description |
|----------|-------------|
| `--version` | Show program's version number and exit. |
| `--interactive` | Run in interactive mode (default if no arguments). |
| `--phrases` | Space‑separated list of phrases. |
| `--phrases-file` | File with one phrase per line (overrides `--phrases`). |
| `--count` | Number of variations to generate (random mode). Default: 1000. |
| `--output` | Output filename (CLI mode). Default: `wordlist.txt`. |
| `--output-dir` | Output directory. Default: `list-maker`. |
| `--exhaustive` | Generate **all** possible case + suffix combos (deterministic). |
| `--max-len` | Max combination length for multiple phrases (2 = pairs, 3 = triples). Default: 3. |
| `--stream` | Stream directly to disk (no dedup, low memory). |
| `--dedup` | Remove duplicates in combined mode (uses more memory). |
| `--seed` | Random seed for reproducibility. |
| `--quiet` | Suppress progress output. |
| `--verbose` | Show detailed logging. |
| `--separators` | Custom separators for combining (e.g., `_` `-` `.`). |
| `--specials` | Custom special characters (e.g., `!` `@` `#`). |
| `--numbers` | Custom number suffixes (e.g., `123` `2024`). |
| `--no-numbers` | Do not append number suffixes. |
| `--no-specials` | Do not append special characters. |
| `--no-suffix` | Do not append any suffix. |
| `--no-title-case` | Exclude title case transformations. |
| `--no-swap-case` | Exclude swap case transformations. |
| **Scraping options** | |
| `--scrape` | One or more topics to scrape (e.g., `--scrape cars soccer`). |
| `--scrape-limit` | Max scraped terms per keyword. Default: 50 (0 = unlimited). |
| `--scrape-min-len` | Minimum character length for scraped terms. Default: 2. |
| **Date options** | |
| `--date` | Generate simple date strings from a date (e.g., `10/9/2014`). |
| `--date-as-suffix` | Append simple date variations as suffixes instead of phrases. |
| `--date-strong` | Generate strong password‑ready date variants (ordinals, specials, separators). |
| `--date-strong-as-suffix` | Append strong date variants as suffixes instead of phrases. |
| **Sample mode** | |
| `--sample N` | Print first N generated lines to stdout (no file output). |

## Advanced Examples

### 1. Company‑specific wordlist with scraped terms and a founding date

```bash
python3 wordlist-maker.py \
  --scrape "acme" "robotics" \
  --scrape-limit 25 \
  --phrases "AcmeCorp" "admin" \
  --date-strong 1/4/2005 \
  --max-len 2 \
  --dedup \
  --count 20000 \
  --output acme_wordlist.txt
```

### 2. Personal birthday wordlist (strong variants as suffixes)

```bash
python3 wordlist-maker.py \
  --phrases "John" "Doe" "password" \
  --date-strong 15/3/1990 \
  --date-strong-as-suffix \
  --specials '!' '?' '#' \
  --count 10000 \
  --output john_birthday.txt
```

### 3. Exhaustive all‑possible combinations for a short list

```bash
python3 wordlist-maker.py \
  --phrases "admin" "root" "user" \
  --exhaustive \
  --max-len 2 \
  --separators '' '_' \
  --no-specials \
  --output exhaustive_admin.txt
```

### 4. Stream a huge wordlist (low memory)

```bash
python3 wordlist-maker.py \
  --phrases "football" "soccer" "team" \
  --max-len 2 \
  --stream \
  --count 5000000 \
  --output huge_sports.txt
```

### 5. Use a file with many phrases

```bash
python3 wordlist-maker.py --phrases-file my_phrases.txt --count 5000 --output from_file.txt
```

## How It Works

1. **Phrase list** – built from manual entries, a file, scraped keywords, or date generators.
2. **Base strings** – for multiple phrases, all ordered permutations (length 2..max_len) joined by separators.
3. **Mutation** – each base string gets a random case transformation and an optional suffix (number, special char, or both).
4. **Output** – written to a text file (one entry per line). Streaming mode writes immediately; set mode stores in memory for deduplication.
5. **Exhaustive mode** – bypasses randomness and generates every possible case + suffix combination deterministically.

## Notes & Limitations

- **Web scraping** relies on `relatedwords.io` – the site’s HTML structure may change. If scraping fails, try a different keyword or install the required libraries.
- **Rate limiting** – the script adds a 0.5s delay between scrape requests to be polite.
- **Exhaustive mode** can generate enormous lists. For a single 6‑letter word with the default numbers (approx. 200) and specials (15), exhaustive mode yields roughly `6 × (1 + 200 + 15 + 200×15 + 15×200) ≈ 6 × 6,430 = 38,580` entries. With multiple words and separators, it grows quickly – use with caution.
- **Deduplication** (`--dedup`) uses a Python `set`; for very large counts, prefer `--stream` to avoid memory issues.
- **Randomness** – use `--seed` to make random‑mode output reproducible.
- **Sample mode** (`--sample`) prints to stdout and ignores `--output` – a warning is shown.
- **Short Hash Suffix** - MD5 is not used for cryptographic purposes in this script. It's in place to generate a short hash suffix to avoid filename collision. 

**This script is provided for educational purposes – use responsibly and only on systems you own or have explicit permission to test.**
