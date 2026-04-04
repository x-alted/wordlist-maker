#!/usr/bin/env python3
"""
Wordlist Maker

Generates password variations from user inputted phrases, dates, and related keywords.
Features:
- Interactive or command-line (CLI) mode
- Single or multiple phrases
- Systematic combination (ordered permutations) with separators
- Case mutations, number suffixes, special characters
- Exhaustive (truly exhaustive, deterministic) mode for complete coverage
- Streaming mode for huge counts (low memory)
- Optional deduplication (--dedup) for combined mode
- Progress bars (tqdm optional), deterministic seeding, logging
- Graceful Ctrl+C handling with partial file cleanup (via signal handler)
- Web scraping: fetch related words from relatedwords.io over HTTPS
- Date mode: generate common date variations (--date)
- Strong date mode: realistic password variants with ordinals, specials, separators (--date-strong)
- Sample mode: preview first N lines without writing a file (--sample)
- Interactive mode improvements: show current phrases, 'back' command

"""

import argparse
import itertools
import logging
import os
import random
import shutil
import sys
import signal
import time
import string
import hashlib
from datetime import datetime
from typing import List, Set, Optional, Callable

# ---------------------------- Version ---------------------------- #
__version__ = "1.1.0"

# ---------------------------- Configuration ---------------------------- #
DEFAULT_OUTPUT_DIR = "wordlist-maker"

# Default number suffixes (unique values only, deterministic order)
COMMON_NUMBERS = ["123", "123456", "123456789", "0", "1", "2", "3", "4", "5", "6", "7", "8", "9"]
NUMBERS_1_100 = [str(i) for i in range(1, 101)]
YEARS_4D = [str(y) for y in range(1930, 2027)]
YEARS_2D = [f"{y:02d}" for y in range(0, 100)]
YEARS_26_30 = [str(y) for y in range(26, 31)]
# Use dict.fromkeys to deduplicate while preserving insertion order
DEFAULT_NUMBER_SUFFIXES = list(dict.fromkeys(
    COMMON_NUMBERS + NUMBERS_1_100 + YEARS_4D + YEARS_2D + YEARS_26_30
))

# Default special characters
DEFAULT_SPECIAL_CHARS = ['!', '@', '#', '$', '%', '^', '&', '*', '?', '-', '_', '+', '=', '~']

# Default separators (empty string = no separator)
DEFAULT_SEPARATORS = ['', '_', '-', '.']

# Suffix types
SUFFIX_TYPES = ['', 'num', 'spec', 'num+spec', 'spec+num']

# ---------------------------- Case Functions ---------------------------- #
def original(s: str) -> str:
    return s

def random_case(s: str) -> str:
    return ''.join(random.choice((c.lower(), c.upper())) for c in s)

# Deterministic case functions (used in exhaustive mode)
DET_CASE_FUNCS: List[Callable[[str], str]] = [
    original,
    str.lower,
    str.upper,
    str.title,
    str.swapcase,
]

# All case functions (including random) for random generation
ALL_CASE_FUNCS: List[Callable[[str], str]] = DET_CASE_FUNCS + [random_case]

# ---------------------------- Helper Functions ---------------------------- #
def sanitize_filename(phrase: str) -> str:
    """Convert a phrase into a safe filename (alphanumeric + underscore)."""
    result = ''.join(c if c.isalnum() else '_' for c in phrase).strip('_')
    return result if result else "wordlist"

def get_positive_int(prompt: str, default: Optional[int] = None) -> int:
    """Interactive: ask for positive integer, optional default on empty input."""
    while True:
        val_str = input(prompt).strip()
        if default is not None and val_str == "":
            return default
        try:
            val = int(val_str)
            if val > 0:
                return val
            print("Please enter a positive integer.")
        except ValueError:
            print("Invalid input.")

def get_bool(prompt: str, default: bool = True) -> bool:
    """Interactive: ask for yes/no, return boolean."""
    while True:
        response = input(prompt).strip().lower()
        if response == '':
            return default
        if response in ('y', 'yes'):
            return True
        if response in ('n', 'no'):
            return False
        print("Please answer y or n.")

def build_base_strings(phrases: List[str], separators: List[str], max_len: int) -> List[str]:
    """
    Build all ordered concatenations of phrases (length 2..max_len)
    using the given separators. Returns list of base strings.
    """
    max_len = min(max_len, len(phrases))
    bases = []
    for L in range(2, max_len + 1):
        for perm in itertools.permutations(phrases, L):
            for sep in separators:
                bases.append(sep.join(perm))
    if not bases:          # less than 2 phrases -> just return phrases as bases
        bases = phrases[:]
    return bases

def generate_suffix(number_suffixes: List[str], special_chars: List[str],
                    allow_numbers: bool, allow_specials: bool, allow_suffix: bool) -> str:
    """
    Return a random suffix based on SUFFIX_TYPES, respecting enabled flags.
    If allow_suffix is False, always return empty string.
    """
    if not allow_suffix:
        return ''
    # Build a filtered list of suffix types based on enabled flags
    enabled_types = []
    if '' in SUFFIX_TYPES:
        enabled_types.append('')
    if allow_numbers and 'num' in SUFFIX_TYPES:
        enabled_types.append('num')
    if allow_specials and 'spec' in SUFFIX_TYPES:
        enabled_types.append('spec')
    if allow_numbers and allow_specials and 'num+spec' in SUFFIX_TYPES:
        enabled_types.append('num+spec')
    if allow_specials and allow_numbers and 'spec+num' in SUFFIX_TYPES:
        enabled_types.append('spec+num')
    if not enabled_types:
        return ''
    stype = random.choice(enabled_types)
    if stype == '':
        return ''
    if stype == 'num':
        return random.choice(number_suffixes)
    if stype == 'spec':
        return random.choice(special_chars)
    if stype == 'num+spec':
        return random.choice(number_suffixes) + random.choice(special_chars)
    if stype == 'spec+num':
        return random.choice(special_chars) + random.choice(number_suffixes)
    return ''

def mutate(base: str, number_suffixes: List[str], special_chars: List[str],
           allow_numbers: bool, allow_specials: bool, allow_suffix: bool,
           case_funcs: List[Callable[[str], str]]) -> str:
    """Apply random case transformation and random suffix."""
    case_func = random.choice(case_funcs)
    suffix = generate_suffix(number_suffixes, special_chars,
                             allow_numbers, allow_specials, allow_suffix)
    return case_func(base) + suffix

# ---------------------------- Date Modes ---------------------------- #
def generate_date_variations(day: int, month: int, year: int) -> List[str]:
    """
    Generate a list of common string representations for a given date.
    Returns a list of date strings (e.g., '100914', '10Sep14', 'September10', etc.)
    """
    # Inputs are already ints; no recasting needed
    year2 = year % 100

    month_names_lower = [
        "jan", "feb", "mar", "apr", "may", "jun",
        "jul", "aug", "sep", "oct", "nov", "dec"
    ]
    month_names_cap = [m.capitalize() for m in month_names_lower]
    month_full_lower = [
        "january", "february", "march", "april", "may", "june",
        "july", "august", "september", "october", "november", "december"
    ]
    month_full_cap = [m.capitalize() for m in month_full_lower]

    mon_lower = month_names_lower[month-1]
    mon_cap = month_names_cap[month-1]
    mon_full_lower = month_full_lower[month-1]
    mon_full_cap = month_full_cap[month-1]

    variations = []

    # Numeric formats
    variations.append(f"{day:02d}{month:02d}{year2:02d}")   # ddmmyy
    variations.append(f"{month:02d}{day:02d}{year2:02d}")   # mmddyy
    variations.append(f"{year}{month:02d}{day:02d}")        # yyyymmdd
    variations.append(f"{day:02d}{month:02d}{year}")        # ddmmyyyy
    variations.append(f"{month:02d}{day:02d}{year}")        # mmddyyyy
    variations.append(f"{year2:02d}{month:02d}{day:02d}")   # yymmdd

    # With separators
    for sep in ['', '-', '/', '.', '_']:
        if sep == '':
            continue  # already have pure numeric above
        variations.append(f"{day:02d}{sep}{month:02d}{sep}{year2:02d}")
        variations.append(f"{month:02d}{sep}{day:02d}{sep}{year2:02d}")
        variations.append(f"{year}{sep}{month:02d}{sep}{day:02d}")
        variations.append(f"{day:02d}{sep}{month:02d}{sep}{year}")
        variations.append(f"{month:02d}{sep}{day:02d}{sep}{year}")

    # Month name + day/year
    for mon in (mon_lower, mon_cap, mon_full_lower, mon_full_cap):
        variations.append(f"{mon}{day:02d}")
        variations.append(f"{mon}{day}")
        variations.append(f"{day}{mon}")
        variations.append(f"{mon}{year}")
        variations.append(f"{mon}{year2:02d}")
        variations.append(f"{day}{mon}{year2:02d}")
        variations.append(f"{day}{mon}{year}")
        variations.append(f"{mon}{day}{year2:02d}")
        variations.append(f"{mon}{day}{year}")

    # Remove duplicates while preserving order
    seen = set()
    unique = []
    for v in variations:
        if v not in seen:
            seen.add(v)
            unique.append(v)
    return unique

def ordinal(n: int) -> str:
    """Return the ordinal string for an integer (e.g., 1 -> '1st', 2 -> '2nd')."""
    if 10 <= n % 100 <= 20:
        return f"{n}th"
    return f"{n}{['th', 'st', 'nd', 'rd', 'th'][min(n % 10, 4)]}"

def generate_strong_date_variations(day: int, month: int, year: int,
                                    specials: List[str], separators: List[str]) -> List[str]:
    """
    Generate a comprehensive list of strong password variants for a given date.
    Includes ordinals, specials, separators, different orders, and common combinations.
    Returns a deterministic order (deduplicated while preserving insertion order).
    """
    year2 = year % 100

    # Month names
    mon_low = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"][month-1]
    mon_cap = mon_low.capitalize()
    mon_full_low = ["january", "february", "march", "april", "may", "june",
                    "july", "august", "september", "october", "november", "december"][month-1]
    mon_full_cap = mon_full_low.capitalize()

    day_ord = ordinal(day)
    day_z = f"{day:02d}"
    month_z = f"{month:02d}"

    # Collect all components
    components = {
        'd': str(day),
        'dd': day_z,
        'dth': day_ord,
        'm': str(month),
        'mm': month_z,
        'mon_low': mon_low,
        'mon_cap': mon_cap,
        'mon_full_low': mon_full_low,
        'mon_full_cap': mon_full_cap,
        'y': str(year),
        'yy': f"{year2:02d}",
    }

    # Define common patterns (order + separators + specials)
    patterns = [
        ['mon_low', 'dth', 'y'],
        ['mon_cap', 'dth', 'y'],
        ['mon_full_low', 'dth', 'y'],
        ['mon_full_cap', 'dth', 'y'],
        ['dth', 'mon_low', 'y'],
        ['dth', 'mon_cap', 'y'],
        ['dth', 'mon_full_low', 'y'],
        ['dth', 'mon_full_cap', 'y'],
        ['y', 'mon_low', 'dth'],
        ['y', 'mon_cap', 'dth'],
        ['y', 'mon_full_low', 'dth'],
        ['y', 'mon_full_cap', 'dth'],
        ['dd', 'mm', 'yy'],
        ['mm', 'dd', 'yy'],
        ['yy', 'mm', 'dd'],
        ['dd', 'mon_low', 'yy'],
        ['mon_low', 'dd', 'yy'],
        ['dd', 'mon_cap', 'yy'],
        ['mon_cap', 'dd', 'yy'],
        ['dd', 'mon_low', 'y'],
        ['mon_low', 'dd', 'y'],
        ['dd', 'mon_cap', 'y'],
        ['mon_cap', 'dd', 'y'],
    ]

    # Use a list to preserve order, then deduplicate with dict.fromkeys
    results = []

    # Generate variations without separators (direct concatenation)
    for pattern in patterns:
        s = ''.join(components[part] for part in pattern)
        results.append(s)

    # With separators
    for sep in separators:
        for pattern in patterns:
            s = sep.join(components[part] for part in pattern)
            results.append(s)

    # Add special characters at the beginning and/or end
    for spec in specials:
        for base in list(results):
            results.append(base + spec)
            results.append(spec + base)
            results.append(base + spec + spec)   # double specials
            results.append(spec + base + spec)

    # Remove duplicates while preserving order
    return list(dict.fromkeys(results))

def parse_date_string(date_str: str) -> tuple:
    """
    Parse a date string in common formats: DD/MM/YYYY, DD-MM-YYYY, DD.MM.YYYY, or with spaces.
    Returns (day, month, year) as integers.
    Raises ValueError if format not recognised or date is invalid.
    """
    for sep in ['/', '-', '.', ' ']:
        if sep in date_str:
            parts = date_str.split(sep)
            if len(parts) == 3:
                try:
                    day = int(parts[0])
                    month = int(parts[1])
                    year = int(parts[2])
                    # Validate using datetime (also catches day/month range errors)
                    datetime(year, month, day)
                    return day, month, year
                except ValueError as e:
                    raise ValueError(f"Invalid date: {date_str} ({e})")
    raise ValueError(f"Could not parse date string '{date_str}'. Use format like 10/9/2014 or 10-09-2014")

# ---------------------------- Keyword Scraper ---------------------------- #
def scrape_related_words(keyword: str, min_length: int = 2, max_results: int = 0) -> List[str]:
    """
    Fetch semantically related terms for a keyword from relatedwords.io over HTTPS.
    Returns a deduplicated list of single-word terms, sanitised.
    """
    try:
        import requests
        from bs4 import BeautifulSoup
    except ImportError:
        raise ImportError(
            "Keyword scraping requires 'requests' and 'beautifulsoup4'.\n"
            "Install them with: pip install requests beautifulsoup4"
        )

    url = f"https://relatedwords.io/{keyword.strip().lower()}"
    try:
        response = requests.get(url, timeout=10, headers={"User-Agent": "wordlist-maker/1.0"})
        response.raise_for_status()
    except requests.RequestException as e:
        raise RuntimeError(f"Failed to fetch related words for '{keyword}': {e}")

    soup = BeautifulSoup(response.text, 'html.parser')
    terms: List[str] = []
    seen: Set[str] = set()
    printable = set(string.printable)

    for li in soup.find_all('li'):
        term = li.get('data-term', '').strip()
        if not term or len(term) < min_length:
            continue
        words = term.split()
        for raw_word in words:
            # Sanitise: strip whitespace, keep only printable characters
            word = ''.join(c for c in raw_word if c in printable).strip()
            if not word or len(word) < min_length:
                continue
            if word not in seen:
                seen.add(word)
                terms.append(word)
        if max_results and len(terms) >= max_results:
            break

    if not terms:
        raise RuntimeError(f"No related terms found for '{keyword}'. Check the keyword or your connection.")

    return terms

# ---------------------------- Exhaustive Mode ---------------------------- #
def exhaustive_mutations(base: str, number_suffixes: List[str], special_chars: List[str],
                         allow_numbers: bool, allow_specials: bool, allow_suffix: bool) -> List[str]:
    results = []
    for case_func in DET_CASE_FUNCS:
        case_var = case_func(base)
        if not allow_suffix:
            results.append(case_var)
            continue
        results.append(case_var)
        if allow_numbers:
            for num in number_suffixes:
                results.append(case_var + num)
        if allow_specials:
            for spec in special_chars:
                results.append(case_var + spec)
        if allow_numbers and allow_specials:
            for num in number_suffixes:
                for spec in special_chars:
                    results.append(case_var + num + spec)
            for spec in special_chars:
                for num in number_suffixes:
                    results.append(case_var + spec + num)
    return list(dict.fromkeys(results))

def exhaustive_combined(phrases: List[str], separators: List[str], max_len: int,
                        number_suffixes: List[str], special_chars: List[str],
                        allow_numbers: bool, allow_specials: bool, allow_suffix: bool) -> List[str]:
    bases = build_base_strings(phrases, separators, max_len)
    seen: dict = {}
    for base in bases:
        for v in exhaustive_mutations(base, number_suffixes, special_chars,
                                      allow_numbers, allow_specials, allow_suffix):
            seen[v] = None
    return list(seen)

# ---------------------------- Streaming / Random Generation ---------------------------- #
def generate_single_stream(base: str, count: int, filepath: str,
                           number_suffixes: List[str], special_chars: List[str],
                           allow_numbers: bool, allow_specials: bool, allow_suffix: bool,
                           case_funcs: List[Callable[[str], str]],
                           progress: bool = False, sample_limit: Optional[int] = None) -> int:
    written = 0
    output_to_stdout = (filepath is None)
    f = sys.stdout if output_to_stdout else open(filepath, 'w', encoding='utf-8')
    try:
        iterator = range(count)
        if progress and not sample_limit:
            try:
                from tqdm import tqdm
                iterator = tqdm(iterator, desc=f"Generating {base}")
            except ImportError:
                pass
        for _ in iterator:
            line = mutate(base, number_suffixes, special_chars,
                          allow_numbers, allow_specials, allow_suffix,
                          case_funcs) + '\n'
            f.write(line)
            written += 1
            if sample_limit and written >= sample_limit:
                break
    finally:
        if not output_to_stdout and f != sys.stdout:
            f.close()
    return written

def generate_single_set(base: str, count: int,
                        number_suffixes: List[str], special_chars: List[str],
                        allow_numbers: bool, allow_specials: bool, allow_suffix: bool,
                        case_funcs: List[Callable[[str], str]],
                        sample_limit: Optional[int] = None) -> List[str]:
    """Generate variations with deduplication, preserving insertion order."""
    seen = {}
    max_attempts = count * 10 if not sample_limit else sample_limit * 10
    attempts = 0
    target = count if not sample_limit else sample_limit
    while len(seen) < target and attempts < max_attempts:
        variation = mutate(base, number_suffixes, special_chars,
                           allow_numbers, allow_specials, allow_suffix,
                           case_funcs)
        if variation not in seen:
            seen[variation] = None
        attempts += 1
    if len(seen) < target:
        logging.warning(f"Only {len(seen)} unique variations possible (wanted {target})")
    return list(seen.keys())

def generate_combined_stream(phrases: List[str], count: int, filepath: str,
                             separators: List[str], max_len: int,
                             number_suffixes: List[str], special_chars: List[str],
                             allow_numbers: bool, allow_specials: bool, allow_suffix: bool,
                             case_funcs: List[Callable[[str], str]],
                             progress: bool = False, sample_limit: Optional[int] = None) -> int:
    base_strings = build_base_strings(phrases, separators, max_len)
    if not base_strings:
        base_strings = phrases[:]

    written = 0
    output_to_stdout = (filepath is None)
    f = sys.stdout if output_to_stdout else open(filepath, 'w', encoding='utf-8')
    try:
        base_cycle = itertools.cycle(base_strings)
        iterator = range(count)
        if progress and not sample_limit:
            try:
                from tqdm import tqdm
                iterator = tqdm(iterator, desc="Combining")
            except ImportError:
                pass
        for _ in iterator:
            base = next(base_cycle)
            line = mutate(base, number_suffixes, special_chars,
                          allow_numbers, allow_specials, allow_suffix,
                          case_funcs) + '\n'
            f.write(line)
            written += 1
            if sample_limit and written >= sample_limit:
                break
    finally:
        if not output_to_stdout and f != sys.stdout:
            f.close()
    return written

def generate_combined_roundrobin(phrases: List[str], count: int,
                                 separators: List[str], max_len: int,
                                 number_suffixes: List[str], special_chars: List[str],
                                 allow_numbers: bool, allow_specials: bool, allow_suffix: bool,
                                 case_funcs: List[Callable[[str], str]],
                                 dedup: bool = False,
                                 progress: bool = False,
                                 sample_limit: Optional[int] = None) -> List[str]:
    base_strings = build_base_strings(phrases, separators, max_len)
    if not base_strings:
        base_strings = phrases[:]

    target = count if not sample_limit else sample_limit

    if dedup:
        variations = {}
        max_attempts = target * 10
        attempts = 0
        if progress:
            try:
                from tqdm import tqdm
                pbar = tqdm(total=target, desc="Combining (dedup)")
            except ImportError:
                pbar = None
        else:
            pbar = None
        for base in itertools.cycle(base_strings):
            if len(variations) >= target or attempts >= max_attempts:
                break
            before = len(variations)
            var = mutate(base, number_suffixes, special_chars,
                         allow_numbers, allow_specials, allow_suffix,
                         case_funcs)
            if var not in variations:
                variations[var] = None
            attempts += 1
            if pbar and len(variations) > before:
                pbar.update(1)
        if pbar:
            pbar.close()
        if len(variations) < target:
            logging.warning(f"Only {len(variations)} unique variations possible (wanted {target})")
        return list(variations.keys())
    else:
        variations = []
        if progress:
            try:
                from tqdm import tqdm
                pbar = tqdm(total=target, desc="Combining")
            except ImportError:
                pbar = None
        else:
            pbar = None
        for base in itertools.cycle(base_strings):
            if len(variations) >= target:
                break
            variations.append(mutate(base, number_suffixes, special_chars,
                                     allow_numbers, allow_specials, allow_suffix,
                                     case_funcs))
            if pbar:
                pbar.update(1)
        if pbar:
            pbar.close()
        return variations

# ---------------------------- File Output ---------------------------- #
def write_wordlist(variations: List[str], filename: str, out_dir: str) -> str:
    os.makedirs(out_dir, exist_ok=True)
    filepath = os.path.join(out_dir, filename)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write('\n'.join(variations) + '\n')
    return filepath

def safe_combined_filename(phrases: List[str], combine_counter: int, max_len: int = 200) -> str:
    """Create a safe filename for combined wordlist, truncating with hash if too long."""
    base = '+'.join(sorted([sanitize_filename(p) for p in phrases]))
    if len(base) <= max_len:
        return f"{base}_{combine_counter}.txt"
    # Truncate and add hash of the full base
    short = base[:max_len-16]  # leave room for hash and counter
    h = hashlib.md5(base.encode()).hexdigest()[:8]
    return f"{short}_{h}_{combine_counter}.txt"

# ---------------------------- Global Cleanup State ---------------------------- #
_current_output_file = None

def signal_handler(sig, frame):
    print("\nInterrupted. Cleaning up...")
    if _current_output_file and os.path.exists(_current_output_file):
        try:
            os.remove(_current_output_file)
            logging.info(f"Removed partial output file: {_current_output_file}")
        except Exception as e:
            logging.error(f"Failed to remove partial file {_current_output_file}: {e}")
    sys.exit(1)

# ---------------------------- Interactive Mode ---------------------------- #
def interactive_mode() -> None:
    signal.signal(signal.SIGINT, signal_handler)
    logging.basicConfig(level=logging.WARNING, format='%(levelname)s: %(message)s')
    print("=== Wordlist Maker (Interactive) ===\n")
    print("Tip: Enter personal facts (pet names, hobbies, loved ones).")
    print("Commands: 'back' to remove last phrase, 'list' to show current phrases, 'done' to finish.\n")

    max_len = get_positive_int("Max combination length (default 3, pairs=2, triples=3): ", default=3)
    use_dedup = get_bool("Remove duplicates in combined mode? (y/N): ", default=False)
    if use_dedup:
        print("Note: Deduplication uses more memory; for huge counts consider streaming (will auto-switch).")

    print("\n--- Suffix settings (appended after the base phrase) ---")
    allow_numbers = get_bool("Append number suffixes? (Y/n): ", default=True)
    allow_specials = get_bool("Append special characters? (Y/n): ", default=True)
    if not allow_numbers and not allow_specials:
        allow_suffix = False
        print("No suffixes will be added (both numbers and specials disabled).")
    else:
        allow_suffix = get_bool("Allow any suffix at all? (Y/n): ", default=True)
        if not allow_suffix:
            print("Suffixes disabled (numbers and specials will be ignored).")
    print()

    large_threshold = 100000

    phrases: List[str] = []
    generated_files: List[str] = []
    combine_counter = 1
    out_dir = DEFAULT_OUTPUT_DIR
    separators = DEFAULT_SEPARATORS
    number_suffixes = DEFAULT_NUMBER_SUFFIXES
    special_chars = DEFAULT_SPECIAL_CHARS
    case_funcs = ALL_CASE_FUNCS

    def show_phrases():
        if phrases:
            print(f"\nCurrent phrases ({len(phrases)}): {', '.join(phrases)}")
        else:
            print("\nNo phrases yet.")

    def add_scraped_phrases_interactive():
        nonlocal phrases
        keyword = input("Topic to scrape (e.g. 'cars', 'football'): ").strip()
        if not keyword:
            print("Topic cannot be empty.")
            return
        limit = get_positive_int("Max terms to import (default 30): ", default=30)
        min_len = get_positive_int("Minimum term length (default 2): ", default=2)
        try:
            terms = scrape_related_words(keyword, min_length=min_len, max_results=limit)
            print(f"Fetched {len(terms)} terms for '{keyword}': {', '.join(terms[:10])}" +
                  (f" ... (+{len(terms)-10} more)" if len(terms) > 10 else ""))
            use_all = get_bool("Add all as separate phrases? (Y/n): ", default=True)
            if use_all:
                for t in terms:
                    if t not in phrases:
                        phrases.append(t)
                print(f"Added {len(terms)} phrases. Total: {len(phrases)}")
            else:
                pick = input("Enter a single term to use: ").strip()
                if pick and pick not in phrases:
                    phrases.append(pick)
                    print(f"Added '{pick}'. Total: {len(phrases)}")
        except (ImportError, RuntimeError) as e:
            print(f"Scrape failed: {e}")

    def add_phrase_manually(phrase: Optional[str] = None):
        nonlocal phrases, generated_files
        if phrase is None:
            phrase = input("Enter phrase: ").strip()
            if not phrase:
                print("Phrase cannot be empty.")
                return
        phrases.append(phrase)
        qty = get_positive_int("How many variations? ")
        safe = sanitize_filename(phrase)
        fname = f"{safe}.txt"
        fpath = os.path.join(out_dir, fname)
        if qty > large_threshold:
            print(f"Large count – using streaming mode (no duplicate removal).")
            written = generate_single_stream(phrase, qty, fpath,
                                             number_suffixes, special_chars,
                                             allow_numbers, allow_specials, allow_suffix,
                                             case_funcs, progress=True)
            generated_files.append(fpath)
            print(f"Streamed {written} lines to: {fpath}\n")
        else:
            vars_list = generate_single_set(phrase, qty,
                                            number_suffixes, special_chars,
                                            allow_numbers, allow_specials, allow_suffix,
                                            case_funcs)
            fpath = write_wordlist(vars_list, fname, out_dir)
            generated_files.append(fpath)
            print(f"Saved {len(vars_list)} variations to: {fpath}\n")
        show_phrases()

    # Main loop
    while True:
        if len(phrases) == 0:
            show_phrases()
            print("\nHow would you like to add your first phrase?")
            print("  [1] Enter a phrase manually")
            print("  [2] Scrape related words for a topic")
            choice = input("Choice (1/2, default 1): ").strip()
            if choice == '2':
                add_scraped_phrases_interactive()
            else:
                if choice and choice not in ('1', ''):
                    add_phrase_manually(phrase=choice)
                else:
                    add_phrase_manually()
            continue

        show_phrases()
        print("\nOptions: [y] add another phrase  [combine] generate combined wordlist  [n] finish  [back] undo last phrase  [list] show phrases")
        choice = input("Choice: ").strip().lower()

        if choice == 'y':
            print("\nAdd phrase by:")
            print("  [1] Manual entry")
            print("  [2] Scrape from topic")
            sub = input("Choice (1/2, default 1): ").strip()
            if sub == '2':
                add_scraped_phrases_interactive()
            else:
                if sub and sub not in ('1', ''):
                    add_phrase_manually(phrase=sub)
                else:
                    add_phrase_manually()
        elif choice == 'combine' and len(phrases) >= 2:
            print(f"Combining phrases: {', '.join(phrases)}")
            qty = get_positive_int("How many combined variations? ")
            fname = safe_combined_filename(phrases, combine_counter)
            combine_counter += 1
            fpath = os.path.join(out_dir, fname)
            if qty > large_threshold:
                print("Large count – using streaming combined mode (no dedup).")
                written = generate_combined_stream(phrases, qty, fpath,
                                                   separators, max_len,
                                                   number_suffixes, special_chars,
                                                   allow_numbers, allow_specials, allow_suffix,
                                                   case_funcs, progress=True)
                generated_files.append(fpath)
                print(f"Streamed {written} lines to: {fpath}\n")
            else:
                print("Generating combined variations...")
                combined = generate_combined_roundrobin(phrases, qty,
                                                        separators, max_len,
                                                        number_suffixes, special_chars,
                                                        allow_numbers, allow_specials, allow_suffix,
                                                        case_funcs,
                                                        dedup=use_dedup,
                                                        progress=True)
                fpath = write_wordlist(combined, fname, out_dir)
                generated_files.append(fpath)
                print(f"Saved {len(combined)} variations to: {fpath}\n")
        elif choice == 'back':
            if phrases:
                removed = phrases.pop()
                print(f"Removed last phrase: '{removed}'")
                show_phrases()
            else:
                print("No phrases to remove.")
        elif choice == 'list':
            show_phrases()
        elif choice == 'n':
            break
        else:
            print("Invalid. Enter y, combine, n, back, or list.")

    if not generated_files:
        print("No wordlists created.")
        return

    print("\nGenerated files:")
    for f in generated_files:
        print(f"  {f}")
    merge = get_bool("\nMerge all into one file? (Y/N): ", default=False)
    if merge:
        print("Note: merge concatenates files as-is; duplicate entries across wordlists are preserved.")
        merged_name = input("Name for merged file (no .txt): ").strip()
        if not merged_name:
            merged_name = "merged"
        merged_name = sanitize_filename(merged_name)
        merged_path = os.path.join(out_dir, f"{merged_name}.txt")
        try:
            with open(merged_path, 'w', encoding='utf-8') as out_f:
                for fpath in generated_files:
                    with open(fpath, 'r', encoding='utf-8') as in_f:
                        shutil.copyfileobj(in_f, out_f)
                        out_f.write('\n')
            print(f"Merged saved to: {merged_path}")
            for fpath in generated_files:
                os.remove(fpath)
            print("Individual files deleted.")
        except Exception as e:
            logging.error(f"Merge failed: {e}")
    else:
        print("Files kept separate.")

# ---------------------------- CLI Mode ---------------------------- #
def cli_mode(args):
    global _current_output_file
    signal.signal(signal.SIGINT, signal_handler)

    out_dir = args.output_dir or DEFAULT_OUTPUT_DIR
    if not args.sample:
        os.makedirs(out_dir, exist_ok=True)

    if args.seed:
        random.seed(args.seed)

    log_level = logging.INFO
    if args.quiet:
        log_level = logging.WARNING
    elif args.verbose:
        log_level = logging.DEBUG
    logging.basicConfig(level=log_level, format='%(levelname)s: %(message)s')

    separators = args.separators if args.separators is not None else DEFAULT_SEPARATORS
    special_chars = args.specials if args.specials is not None else DEFAULT_SPECIAL_CHARS
    number_suffixes = args.numbers if args.numbers is not None else DEFAULT_NUMBER_SUFFIXES

    allow_numbers = not args.no_numbers
    allow_specials = not args.no_specials
    allow_suffix = not args.no_suffix

    # Build case functions list with filtering (deduplicated)
    if args.exhaustive:
        case_funcs = DET_CASE_FUNCS.copy()
    else:
        case_funcs = ALL_CASE_FUNCS.copy()
    if args.no_title_case:
        case_funcs = [f for f in case_funcs if f is not str.title]
    if args.no_swap_case:
        case_funcs = [f for f in case_funcs if f is not str.swapcase]

    max_len = min(args.max_len, len(args.phrases))

    if args.sample:
        sample_limit = args.sample
        out_file = None
    else:
        sample_limit = None
        out_file = os.path.join(out_dir, args.output)
        # Set global for cleanup during streaming
        _current_output_file = out_file

    try:
        if args.exhaustive:
            if args.count != 1000:
                logging.warning("--count is ignored in exhaustive mode; all combinations will be generated.")
            logging.info("Using exhaustive mode (deterministic case transforms only).")
            if len(args.phrases) == 1:
                variations = exhaustive_mutations(args.phrases[0], number_suffixes, special_chars,
                                                  allow_numbers, allow_specials, allow_suffix)
            else:
                logging.warning("Exhaustive combined mode is fully in-memory; may use significant RAM for many phrases or large suffix sets.")
                variations = exhaustive_combined(args.phrases, separators, max_len,
                                                 number_suffixes, special_chars,
                                                 allow_numbers, allow_specials, allow_suffix)
            if args.sample:
                for v in variations[:sample_limit]:
                    print(v)
                logging.info(f"Printed {min(sample_limit, len(variations))} sample lines.")
            else:
                with open(out_file, 'w', encoding='utf-8') as f:
                    f.write('\n'.join(variations) + '\n')
                logging.info(f"Exhaustive generation complete: {len(variations)} entries -> {out_file}")
        else:
            if len(args.phrases) == 1:
                logging.info(f"Generating {args.count} variations for '{args.phrases[0]}'")
                if args.stream or args.sample:
                    written = generate_single_stream(args.phrases[0], args.count, out_file,
                                                     number_suffixes, special_chars,
                                                     allow_numbers, allow_specials, allow_suffix,
                                                     case_funcs,
                                                     progress=not args.quiet,
                                                     sample_limit=sample_limit)
                    if args.sample:
                        logging.info(f"Printed {written} sample lines.")
                    else:
                        logging.info(f"Streamed {written} lines to {out_file}")
                else:
                    variations = generate_single_set(args.phrases[0], args.count,
                                                     number_suffixes, special_chars,
                                                     allow_numbers, allow_specials, allow_suffix,
                                                     case_funcs,
                                                     sample_limit=sample_limit)
                    if args.sample:
                        for v in variations:
                            print(v)
                        logging.info(f"Printed {len(variations)} sample lines.")
                    else:
                        with open(out_file, 'w', encoding='utf-8') as f:
                            f.write('\n'.join(variations) + '\n')
                        logging.info(f"Saved {len(variations)} entries to {out_file}")
            else:
                logging.info(f"Combining {len(args.phrases)} phrases, count={args.count}, max_len={max_len}")
                if args.stream or args.sample:
                    written = generate_combined_stream(args.phrases, args.count, out_file,
                                                       separators, max_len,
                                                       number_suffixes, special_chars,
                                                       allow_numbers, allow_specials, allow_suffix,
                                                       case_funcs,
                                                       progress=not args.quiet,
                                                       sample_limit=sample_limit)
                    if args.sample:
                        logging.info(f"Printed {written} sample lines.")
                    else:
                        logging.info(f"Streamed {written} lines to {out_file}")
                else:
                    variations = generate_combined_roundrobin(args.phrases, args.count,
                                                              separators, max_len,
                                                              number_suffixes, special_chars,
                                                              allow_numbers, allow_specials, allow_suffix,
                                                              case_funcs,
                                                              dedup=args.dedup,
                                                              progress=not args.quiet,
                                                              sample_limit=sample_limit)
                    if args.sample:
                        for v in variations:
                            print(v)
                        logging.info(f"Printed {len(variations)} sample lines.")
                    else:
                        with open(out_file, 'w', encoding='utf-8') as f:
                            f.write('\n'.join(variations) + '\n')
                        logging.info(f"Saved {len(variations)} entries to {out_file}")
    except KeyboardInterrupt:
        signal_handler(None, None)
    except Exception as e:
        logging.error(f"Generation failed: {e}")
        if out_file and os.path.exists(out_file):
            try:
                os.remove(out_file)
                logging.info(f"Removed partial output file: {out_file}")
            except Exception:
                pass
        sys.exit(1)
    finally:
        if not args.sample:
            _current_output_file = None

# ---------------------------- Main Entry ---------------------------- #
def main():
    parser = argparse.ArgumentParser(description="Generate password wordlists for CTFs")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--interactive", action="store_true", help="Run in interactive mode (default if no arguments)")
    parser.add_argument("--phrases", nargs="+", help="List of phrases (for CLI mode)")
    parser.add_argument("--phrases-file", type=str, help="File containing one phrase per line (overrides --phrases)")
    parser.add_argument("--count", type=int, default=1000, help="Number of variations (random mode)")
    parser.add_argument("--output", default="wordlist.txt", help="Output filename (CLI mode)")
    parser.add_argument("--output-dir", help="Output directory (default: wordlist-maker)")
    parser.add_argument("--exhaustive", action="store_true", help="Generate ALL possible combinations (deterministic case only)")
    parser.add_argument("--max-len", type=int, default=3, help="Max combination length for multiple phrases (default 3)")
    parser.add_argument("--stream", action="store_true", help="Stream output directly to disk (no dedup, low memory)")
    parser.add_argument("--dedup", action="store_true", help="Remove duplicates in combined mode (uses more memory)")
    parser.add_argument("--seed", type=int, help="Random seed for reproducibility")
    parser.add_argument("--quiet", action="store_true", help="Suppress progress output")
    parser.add_argument("--verbose", action="store_true", help="Show detailed logging")
    parser.add_argument("--separators", nargs="+", default=None, help="Custom separators (e.g., '_' '-' '.'). Use quotes if spaces.")
    parser.add_argument("--specials", nargs="+", default=None, help="Custom special characters (e.g., '!' '@' '#')")
    parser.add_argument("--numbers", nargs="+", default=None, help="Custom number suffixes (e.g., '123' '2024')")
    parser.add_argument("--no-numbers", action="store_true", help="Do not append number suffixes")
    parser.add_argument("--no-specials", action="store_true", help="Do not append special characters")
    parser.add_argument("--no-suffix", action="store_true", help="Do not append any suffix (numbers or specials)")
    parser.add_argument("--no-title-case", action="store_true", help="Exclude title case transformations")
    parser.add_argument("--no-swap-case", action="store_true", help="Exclude swap case transformations")

    # Scraping arguments
    parser.add_argument("--scrape", nargs="+", metavar="KEYWORD",
                        help="Scrape related words for topic(s) and use as phrases (e.g. --scrape cars soccer)")
    parser.add_argument("--scrape-limit", type=int, default=50, metavar="N",
                        help="Max scraped terms per keyword (default: 50, 0 = unlimited)")
    parser.add_argument("--scrape-min-len", type=int, default=2, metavar="N",
                        help="Minimum character length for scraped terms (default: 2)")

    # Date modes
    parser.add_argument("--date", type=str, metavar="DATE",
                        help="Generate simple date variations from a date (e.g. 10/9/2014). Added as phrases.")
    parser.add_argument("--date-as-suffix", action="store_true",
                        help="If --date is used, append date variations as suffixes instead of adding as phrases.")
    parser.add_argument("--date-strong", type=str, metavar="DATE",
                        help="Generate strong password variants for a date (e.g. 10/9/2014). Includes ordinals, specials, separators.")
    parser.add_argument("--date-strong-as-suffix", action="store_true",
                        help="If --date-strong is used, append the variants as suffixes instead of adding as phrases.")

    # Sample mode
    parser.add_argument("--sample", type=int, metavar="N",
                        help="Print first N generated lines to stdout (no file output).")

    args = parser.parse_args()

    # Validate --count
    if args.count <= 0:
        parser.error("--count must be a positive integer")

    # Load phrases from file if given
    if args.phrases_file:
        try:
            with open(args.phrases_file, 'r', encoding='utf-8') as f:
                args.phrases = [line.strip() for line in f if line.strip()]
            if not args.phrases:
                print("Error: phrases file is empty.")
                sys.exit(1)
        except Exception as e:
            print(f"Error reading phrases file: {e}")
            sys.exit(1)

    # Handle scraping
    if args.scrape:
        scraped_terms: List[str] = []
        for kw in args.scrape:
            try:
                logging.info(f"Scraping related words for: '{kw}'")
                terms = scrape_related_words(kw, min_length=args.scrape_min_len,
                                             max_results=args.scrape_limit)
                logging.info(f"  -> {len(terms)} terms found")
                scraped_terms.extend(terms)
                time.sleep(0.5)
            except (ImportError, RuntimeError) as e:
                print(f"Error: {e}")
                sys.exit(1)
        existing = list(args.phrases) if args.phrases else []
        combined = list(dict.fromkeys(existing + scraped_terms))
        args.phrases = combined
        logging.info(f"Total phrases after scraping: {len(args.phrases)}")

    # Handle simple date mode
    if args.date:
        try:
            day, month, year = parse_date_string(args.date)
            date_variations = generate_date_variations(day, month, year)
            if args.date_as_suffix:
                if args.numbers is None:
                    args.numbers = []
                args.numbers.extend(date_variations)
                logging.info(f"Added {len(date_variations)} date variations as suffixes.")
            else:
                existing = list(args.phrases) if args.phrases else []
                combined = list(dict.fromkeys(existing + date_variations))
                args.phrases = combined
                logging.info(f"Added {len(date_variations)} date variations as phrases. Total phrases: {len(args.phrases)}")
        except ValueError as e:
            print(f"Error parsing date: {e}")
            sys.exit(1)

    # Handle strong date mode
    if args.date_strong:
        try:
            day, month, year = parse_date_string(args.date_strong)
            specials = args.specials if args.specials is not None else DEFAULT_SPECIAL_CHARS
            separators = args.separators if args.separators is not None else DEFAULT_SEPARATORS
            strong_variants = generate_strong_date_variations(day, month, year, specials, separators)
            logging.info(f"Generated {len(strong_variants)} strong date variants for {args.date_strong}")

            if args.date_strong_as_suffix:
                if args.numbers is None:
                    args.numbers = []
                args.numbers.extend(strong_variants)
                logging.info(f"Added {len(strong_variants)} date variants as suffixes.")
            else:
                existing = list(args.phrases) if args.phrases else []
                combined = list(dict.fromkeys(existing + strong_variants))
                args.phrases = combined
                logging.info(f"Added {len(strong_variants)} date variants as phrases. Total phrases: {len(args.phrases)}")
        except ValueError as e:
            print(f"Error parsing date: {e}")
            sys.exit(1)

    # Check exhaustive mode without phrases
    if args.exhaustive and not args.phrases:
        parser.error("--exhaustive requires at least one phrase via --phrases")

    if args.interactive or (not args.phrases and not args.exhaustive):
        if args.phrases_file and args.interactive:
            print("Warning: --interactive is ignored because --phrases-file was provided; running CLI mode.")
        elif args.phrases_file:
            pass
        else:
            interactive_mode()
            return

    if not args.phrases:
        parser.error("CLI mode requires --phrases (or --phrases-file) or --interactive")

    # Warn if --sample is used with --output
    if args.sample and args.output:
        logging.info("--sample is set; ignoring --output (printing to stdout instead).")
        args.output = None

    cli_mode(args)

if __name__ == "__main__":
    main()
