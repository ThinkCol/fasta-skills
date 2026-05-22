#!/usr/bin/env python3
"""
Lenx Wordcloud Generator
Reads a TSV file of sentiment_score\tlang_abbr\tpost_message lines, applies filters,
tokenizes text (jieba for CJK, whitespace for others), and generates a wordcloud PNG.

Stopwords are loaded from external files:
  - scripts/stopword_en.txt     (English)
  - scripts/stopword_zh-t.txt   (Traditional Chinese)
  - scripts/stopword_zh-s.txt   (Simplified Chinese)
"""

import argparse
import json
import os
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime

# ---------------------------------------------------------------------------
# Stopword loading from external files
# ---------------------------------------------------------------------------

_STOPWORD_DIR = os.path.dirname(os.path.abspath(__file__))

_STOPWORD_FILES = {
    "en": os.path.join(_STOPWORD_DIR, "stopword_en.txt"),
    "zh-t": os.path.join(_STOPWORD_DIR, "stopword_zh-t.txt"),
    "zh-s": os.path.join(_STOPWORD_DIR, "stopword_zh-s.txt"),
}

_FALLBACK_LANG = "zh-t"


def _load_stopwords(filepath: str) -> set[str]:
    """Load stopwords from a text file, one per line."""
    stopwords: set[str] = set()
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                word = line.strip()
                if word:
                    stopwords.add(word.lower())
    except FileNotFoundError:
        print(f"Warning: Stopword file not found: {filepath}", file=sys.stderr)
    return stopwords


def _load_all_stopwords() -> dict[str, set[str]]:
    """Load all stopword files at startup."""
    result: dict[str, set[str]] = {}
    for lang, path in _STOPWORD_FILES.items():
        result[lang] = _load_stopwords(path)
    return result


def _get_stopwords(
    lang_abbr: str, stopword_map: dict[str, set[str]]
) -> set[str]:
    """Get the appropriate stopword set for a language code."""
    lang = lang_abbr.strip().lower() if lang_abbr else ""
    if lang in stopword_map:
        return stopword_map[lang]
    # Fallback
    return stopword_map.get(_FALLBACK_LANG, set())


# ---------------------------------------------------------------------------
# URL stripping
# ---------------------------------------------------------------------------


def _strip_urls(text: str) -> str:
    """Remove URLs from text so they don't contribute tokens."""
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'www\.\S+', '', text)
    return text


# ---------------------------------------------------------------------------
# CJK detection
# ---------------------------------------------------------------------------


def _has_cjk(text: str) -> bool:
    """Check if text contains CJK Unified Ideographs."""
    for ch in text:
        cp = ord(ch)
        if 0x4E00 <= cp <= 0x9FFF or 0x3400 <= cp <= 0x4DBF:
            return True
    return False


# ---------------------------------------------------------------------------
# CJK font discovery
# ---------------------------------------------------------------------------

_CJK_FONT_CANDIDATES = [
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/noto-cjk/NotoSerifCJK-Regular.ttc",
    "/usr/share/fonts/adobe-source-han-sans/SourceHanSansCN-Regular.otf",
    "/usr/share/fonts/adobe-source-han-sans/SourceHanSansTC-Regular.otf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/TTF/odokai.ttf",
    "/usr/share/fonts/TTF/odosung.ttc",
]


def _find_cjk_font() -> str | None:
    """Find the first available CJK font on the system."""
    for path in _CJK_FONT_CANDIDATES:
        if os.path.exists(path):
            return path
    try:
        result = subprocess.run(
            ["fc-match", "-f", "%{file}", "sans-serif:lang=zh"],
            capture_output=True, text=True, timeout=5
        )
        path = result.stdout.strip()
        if path and os.path.exists(path):
            return path
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


# ---------------------------------------------------------------------------
# Tokenization
# ---------------------------------------------------------------------------


def _tokenize(text: str) -> list[str]:
    """Tokenize text: jieba for CJK content, regex word split otherwise."""
    if _has_cjk(text):
        import jieba
        return list(jieba.cut(text, cut_all=False))
    else:
        return re.findall(r"[a-zA-Z0-9\u00C0-\u024F']+(?:[-'][a-zA-Z0-9]+)*", text.lower())


# ---------------------------------------------------------------------------
# Token filters
# ---------------------------------------------------------------------------


def _is_noise(token: str) -> bool:
    """Check if a token is noise and should be excluded."""
    t = token.strip()
    if not t:
        return True
    # Too short
    if len(t) < 2:
        return True
    # Too long
    if len(t) > 30:
        return True
    # Only digits / numbers with punctuation
    if re.match(r"^[\d.,%$€£¥+-]+$", t):
        return True
    # Mentions and hashtags
    if t.startswith(("@", "#")):
        return True
    return False


def _filter_by_keywords(text: str, include: list[str] | None, exclude: list[str] | None) -> bool:
    """Return True if text passes the keyword filter."""
    text_lower = text.lower()
    if include:
        if not any(kw.lower() in text_lower for kw in include):
            return False
    if exclude:
        if any(kw.lower() in text_lower for kw in exclude):
            return False
    return True


# ---------------------------------------------------------------------------
# Sentiment
# ---------------------------------------------------------------------------


_SENTIMENT_NEG_THRESHOLD = -0.35
_SENTIMENT_POS_THRESHOLD = 0.35


def _classify_sentiment(score_str: str) -> str | None:
    """Classify a sentiment score string into positive/negative/neutral."""
    s = score_str.strip()
    if not s:
        return None
    try:
        score = float(s)
    except ValueError:
        return None
    if score < _SENTIMENT_NEG_THRESHOLD:
        return "negative"
    elif score > _SENTIMENT_POS_THRESHOLD:
        return "positive"
    else:
        return "neutral"


def _passes_sentiment_filter(score_str: str, filter_sentiment: str | None) -> bool:
    """Return True if the record passes the sentiment filter."""
    if filter_sentiment is None:
        return True
    actual = _classify_sentiment(score_str)
    if actual is None:
        return filter_sentiment == "neutral"
    return actual == filter_sentiment


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Generate wordcloud from Lenx task data")
    parser.add_argument("--input", required=True, help="Path to input TSV (sentiment_score tab lang_abbr tab post_message)")
    parser.add_argument("--output", required=True, help="Path to output PNG")
    parser.add_argument("--metadata", required=True, help="Path to output metadata JSON")
    parser.add_argument("--max-words", type=int, default=200, help="Max words in wordcloud")
    parser.add_argument("--width", type=int, default=1920, help="Image width")
    parser.add_argument("--height", type=int, default=1080, help="Image height")
    parser.add_argument("--colormap", default="viridis", help="Matplotlib colormap")
    parser.add_argument("--background", default="white", help="Background color")
    parser.add_argument("--include", help="Comma-separated keywords to include")
    parser.add_argument("--exclude", help="Comma-separated keywords to exclude")
    parser.add_argument("--sentiment", choices=["positive", "negative", "neutral"], help="Sentiment filter")
    parser.add_argument("--extra-stopwords", help="Comma-separated extra stopwords")
    parser.add_argument("--font-path", help="Path to font file for wordcloud (auto-detected for CJK if not specified)")
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"ERROR: Input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    # Load stopword files at startup
    stopword_map = _load_all_stopwords()
    extra_stopwords: set[str] = set()
    if args.extra_stopwords:
        extra_stopwords = {w.strip().lower() for w in args.extra_stopwords.split(",") if w.strip()}

    include_list = [kw.strip() for kw in args.include.split(",")] if args.include else None
    exclude_list = [kw.strip() for kw in args.exclude.split(",")] if args.exclude else None

    total_lines = 0
    filtered_lines = 0
    sentiment_counts = {"positive": 0, "neutral": 0, "negative": 0}
    all_tokens: list[str] = []
    total_before_filter = 0

    with open(args.input, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            total_lines += 1
            total_before_filter += 1

            # Parse 3-column TSV: sentiment_score\tlang_abbr\tpost_message
            parts = line.split("\t", 2)
            if len(parts) == 3:
                score_str, lang_abbr, message = parts
            elif len(parts) == 2:
                # Backward compat: 2-column format (score\tmessage), no lang info
                score_str, message = parts
                lang_abbr = ""
            else:
                score_str = ""
                lang_abbr = ""
                message = parts[0]

            # Keyword filter
            if not _filter_by_keywords(message, include_list, exclude_list):
                filtered_lines += 1
                continue

            # Sentiment filter
            if not _passes_sentiment_filter(score_str, args.sentiment):
                filtered_lines += 1
                continue

            # Track sentiment distribution
            sent = _classify_sentiment(score_str)
            if sent:
                sentiment_counts[sent] += 1

            # Strip URLs
            message = _strip_urls(message)

            # Tokenize
            tokens = _tokenize(message)

            # Load appropriate stopwords for this post's language
            # Always include English stopwords to handle code-switching (e.g., zh-t posts
            # containing English words like "the", "is", "and")
            lang_stopwords = _get_stopwords(lang_abbr, stopword_map)
            stopwords = stopword_map.get("en", set()) | lang_stopwords | extra_stopwords

            # Filter tokens
            clean = [
                t.lower().strip()
                for t in tokens
                if not _is_noise(t) and t.lower().strip() not in stopwords
            ]
            all_tokens.extend(clean)

    if total_lines == 0:
        print("ERROR: No data found in input file", file=sys.stderr)
        sys.exit(1)

    word_freq = Counter(all_tokens)

    if not word_freq:
        print(
            "ERROR: No words remained after filtering. Try relaxing filters.",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        from wordcloud import WordCloud
        import matplotlib.pyplot as plt
    except ImportError as e:
        print(
            f"ERROR: Missing required package: {e}. Install with: pip install wordcloud matplotlib pillow jieba",
            file=sys.stderr,
        )
        sys.exit(1)

    font_path = args.font_path
    if font_path is None:
        font_path = _find_cjk_font()

    wc = WordCloud(
        font_path=font_path,
        width=args.width,
        height=args.height,
        max_words=args.max_words,
        background_color=args.background,
        colormap=args.colormap,
        font_step=1,
        prefer_horizontal=0.7,
        collocations=False,
    ).generate_from_frequencies(word_freq)

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    wc.to_file(args.output)

    top_20 = [{"word": w, "count": c} for w, c in word_freq.most_common(20)]

    metadata = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "wordcloud_file": os.path.basename(args.output),
        "total_posts_fetched": total_before_filter,
        "posts_after_filter": total_lines - filtered_lines,
        "posts_filtered_out": filtered_lines,
        "include_keywords": include_list or [],
        "exclude_keywords": exclude_list or [],
        "sentiment_filter": args.sentiment,
        "sentiment_distribution": sentiment_counts,
        "max_words": args.max_words,
        "image_width": args.width,
        "image_height": args.height,
        "colormap": args.colormap,
        "top_20_words": top_20,
        "total_unique_words": len(word_freq),
    }

    os.makedirs(os.path.dirname(args.metadata) or ".", exist_ok=True)
    with open(args.metadata, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    posts_used = total_lines - filtered_lines
    print(f"Wordcloud generated: {args.output}")
    print(f"Posts fetched: {total_before_filter}")
    print(f"Posts used: {posts_used}")
    print(f"Total unique words: {len(word_freq)}")
    print(f"Top 5 words: {', '.join(f'{w['word']} ({w['count']})' for w in top_20[:5])}")
    print(f"Sentiment distribution: {json.dumps(sentiment_counts)}")


if __name__ == "__main__":
    main()
