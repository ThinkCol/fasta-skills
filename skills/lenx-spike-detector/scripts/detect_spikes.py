#!/usr/bin/env python3
"""
Lenx Task Spike Detector
Reads a TSV of Lenx post data (unix_timestamp, post_message, ai_sentiment,
sentiment_score, reaction_count, comment_count, share_count, view_count,
lang_abbr, site, post_link, thread_title), buckets posts over time, and
detects activity spikes per metric (volume, sentiment, engagement, topic)
using a robust MAD-based z-score (robust_z).

Outputs:
  - a metadata JSON file with per-bucket series and detected spikes
  - a matplotlib PNG chart of the series with spikes marked (unless --no-chart)
  - a markdown or text report describing each spike

Dependencies: Python 3 stdlib only; matplotlib (optional, for charts);
jieba (optional, for Chinese topic auto-discovery).
"""

import argparse
import json
import math
import os
import re
import statistics
import sys
from collections import Counter
from datetime import datetime

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BUCKET_MS = {"hourly": 3600000, "6h": 21600000, "daily": 86400000}
BUCKET_LABELS = {"hourly": "1h", "6h": "6h", "daily": "24h"}
SENTIMENT_CLASSES = ("negative", "positive", "neutral")
MAX_SAMPLES_PER_BUCKET = 10
MAX_SAMPLE_POSTS_PER_SPIKE = 3
MAX_SAMPLE_LINKS_PER_SPIKE = 5
MAX_TOP_SPIKING_TOPICS = 5

_BUILTIN_STOPWORDS = {
    "the", "and", "for", "are", "but", "not", "you", "all", "any", "can",
    "had", "her", "was", "one", "our", "out", "day", "get", "has", "him",
    "his", "how", "man", "new", "now", "old", "see", "two", "way", "who",
    "boy", "did", "its", "let", "put", "say", "she", "too", "use", "that",
    "with", "have", "this", "will", "your", "from", "they", "know", "want",
    "been", "good", "much", "some", "time", "very", "when", "come", "here",
    "just", "like", "long", "make", "many", "more", "only", "over", "such",
    "take", "than", "them", "well", "were", "what", "which", "while",
    "about", "could", "would", "their", "there", "these", "where", "think",
    "because", "people", "things", "thing", "really", "should", "little",
}

_TIME_FMT = "%Y-%m-%d %H:%M"


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _to_int(value) -> int:
    """Coerce a value to int, returning 0 for anything unusable."""
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _fmt_time(ms: int) -> str:
    """Format a Unix millisecond timestamp as 'YYYY-MM-DD HH:MM'."""
    return datetime.fromtimestamp(ms / 1000).strftime(_TIME_FMT)


def _fmt_num(value: float) -> str:
    """Format a number as int when whole, else with one decimal."""
    if value is None:
        return "-"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return f"{value:.1f}"


def _has_cjk(text: str) -> bool:
    """Check if text contains CJK Unified Ideographs."""
    for ch in text:
        cp = ord(ch)
        if 0x4E00 <= cp <= 0x9FFF or 0x3400 <= cp <= 0x4DBF:
            return True
    return False


def _tokenize(message: str) -> list[str]:
    """Tokenize a message: jieba for CJK text, regex words otherwise.

    Falls back to whitespace splitting for CJK text when jieba is unavailable.
    """
    if _has_cjk(message):
        try:
            import jieba
            return list(jieba.cut(message, cut_all=False))
        except ImportError:
            return message.split()
    return re.findall(r"[A-Za-z][A-Za-z0-9'-]*", message.lower())


def _load_stopwords(filepath: str) -> set[str]:
    """Load stopwords from a file (one per line), falling back to a built-in set."""
    if filepath and os.path.exists(filepath):
        stopwords: set[str] = set()
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                word = line.strip().lower()
                if word:
                    stopwords.add(word)
        return stopwords
    print(f"Warning: stopword file not found: {filepath}; using built-in set", file=sys.stderr)
    return set(_BUILTIN_STOPWORDS)


def _clean_tokens(tokens: list[str], stopwords: set[str]) -> list[str]:
    """Drop stopwords, tokens shorter than 3 chars, and pure numbers."""
    clean = []
    for token in tokens:
        t = token.lower()
        if len(t) < 3:
            continue
        if t in stopwords:
            continue
        if re.fullmatch(r"\d+", t):
            continue
        clean.append(t)
    return clean


# ---------------------------------------------------------------------------
# TSV loading
# ---------------------------------------------------------------------------


def _load_tsv(path: str) -> list[dict]:
    """Load the TSV: a '#...' header line followed by tab-delimited rows.

    Rows that do not match the header width are skipped.
    """
    rows: list[dict] = []
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        header = None
        for line in f:
            line = line.rstrip("\n").rstrip("\r")
            if not line.strip():
                continue
            if header is None:
                if line.startswith("#"):
                    line = line[1:]
                header = line.split("\t")
                continue
            parts = line.split("\t")
            if len(parts) != len(header):
                continue
            rows.append(dict(zip(header, parts)))
    return rows


# ---------------------------------------------------------------------------
# Robust spike detection (MAD-based)
# ---------------------------------------------------------------------------


def detect_spikes(values: list[float], sensitivity: float) -> list[dict]:
    """Detect spikes in a series using a robust MAD-based z-score.

    A bucket is a spike when its robust_z exceeds `sensitivity` AND its value
    is at least the min_count guard (max(3, 10% of median), 3 when median is 0).
    Returns entries without timestamps; the caller attaches bucket windows.
    """
    n = len(values)
    if n == 0:
        return []
    median = statistics.median(values)
    deviations = [abs(v - median) for v in values]
    mad = statistics.median(deviations)
    sigma_hat = 1.4826 * mad
    if sigma_hat == 0:
        sigma_hat = statistics.pstdev(values)  # fallback for flat/sparse baselines where MAD is 0
    min_count = max(3, int(0.1 * median)) if median > 0 else 3
    spikes = []
    for i, v in enumerate(values):
        robust_z = (v - median) / sigma_hat if sigma_hat > 0 else 0.0
        if robust_z > sensitivity and v >= min_count:
            spikes.append(
                {
                    "bucket_index": i,
                    "value": int(v),
                    "median": median,
                    "ratio": (v / median) if median > 0 else None,
                    "robust_z": round(robust_z, 3),
                }
            )
    return spikes


def _attach_times(spike: dict, from_ms: int, bucket_ms: int) -> dict:
    """Add the bucket time window (ms + ISO-ish strings) to a spike entry."""
    start = from_ms + spike["bucket_index"] * bucket_ms
    spike["from_ts"] = start
    spike["to_ts"] = start + bucket_ms
    spike["from_iso"] = _fmt_time(start)
    spike["to_iso"] = _fmt_time(start + bucket_ms)
    return spike


# ---------------------------------------------------------------------------
# Bucket aggregation
# ---------------------------------------------------------------------------


def _bucket_index(ts: int, from_ms: int, bucket_ms: int, num_buckets: int) -> int:
    """Map a timestamp to a bucket index, clamped to the valid range."""
    idx = (ts - from_ms) // bucket_ms
    return max(0, min(num_buckets - 1, idx))


def _new_metric(num_buckets: int) -> dict:
    """Create a per-bucket aggregation structure for one metric."""
    return {
        "series": [0] * num_buckets,
        "sites": [Counter() for _ in range(num_buckets)],
        "samples": [[] for _ in range(num_buckets)],
    }


def _add_sample(samples: list[dict], record: dict) -> None:
    """Store a compact sample (link, truncated message, sentiment) if room."""
    if len(samples) < MAX_SAMPLES_PER_BUCKET:
        samples.append(
            {
                "link": record["link"],
                "message": record["message"][:160],
                "sentiment": record["sentiment"],
            }
        )


def _enrich_spike(spike: dict, metric: dict, sentiment_buckets: list[Counter], from_ms: int, bucket_ms: int, sentiment_override: list[Counter] | None = None) -> dict:
    """Add time window, top sites, sentiment breakdown, and sample posts."""
    _attach_times(spike, from_ms, bucket_ms)
    idx = spike["bucket_index"]
    spike["top_sites"] = [
        {"site": site, "count": count}
        for site, count in metric["sites"][idx].most_common(3)
    ]
    buckets_for_breakdown = sentiment_override if sentiment_override is not None else sentiment_buckets
    breakdown = {sent: count for sent, count in buckets_for_breakdown[idx].items() if count}
    spike["sentiment_breakdown"] = breakdown
    spike["sample_posts"] = metric["samples"][idx][:MAX_SAMPLE_POSTS_PER_SPIKE]
    spike["sample_post_links"] = [s["link"] for s in metric["samples"][idx]][:MAX_SAMPLE_LINKS_PER_SPIKE]
    return spike


# ---------------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------------


def _spike_table_rows(spikes: list[dict]) -> list[list[str]]:
    rows = []
    for s in spikes:
        ratio = f"{s['ratio']:.1f}x" if s["ratio"] is not None else "-"
        rows.append(
            [
                f"{s['from_iso']} - {s['to_iso']}",
                _fmt_num(s["value"]),
                _fmt_num(s["median"]),
                ratio,
                f"{s['robust_z']:.2f}",
            ]
        )
    return rows


def _append_spike_table(lines: list[str], headers: list[str], spikes: list[dict]) -> None:
    """Append a markdown table of spike rows to a line list."""
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("|" + "|".join(["---"] * len(headers)) + "|")
    for row in _spike_table_rows(spikes):
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")


def _metric_bullets(spike: dict) -> list[str]:
    """Shared bullet lines describing a single spike."""
    lines = []
    sites = ", ".join(f"{s['site']} ({s['count']})" for s in spike["top_sites"]) or "n/a"
    lines.append(f"Top sites: {sites}")
    breakdown = ", ".join(f"{k}: {v}" for k, v in spike["sentiment_breakdown"].items()) or "n/a"
    lines.append(f"Sentiment: {breakdown}")
    for sample in spike["sample_posts"]:
        lines.append(f'"{sample["message"]}" — {sample["link"]}')
    return lines


def _render_markdown(args, meta: dict, series: dict, spikes: dict, top_spiking_topics: list[dict], topic_keywords: list[str]) -> str:
    lines = [f"# Spike Detection Report — Task {args.task_id}", ""]
    lines.append(f"- **Time range:** {meta['time_range_label']}")
    lines.append(f"- **Bucket:** {meta['bucket']['bucket_label']} ({meta['bucket']['num_buckets']} buckets)")
    lines.append(f"- **Total records:** {meta['total_records']}")
    lines.append(f"- **Sensitivity (robust z):** {args.sensitivity}")
    lines.append(f"- **Metrics:** {', '.join(sorted(meta['metrics_requested']))}")
    lines.append(f"- **Sentiment target:** {args.sentiment}")
    lines.append(f"- **Topic filter:** {', '.join(topic_keywords) if topic_keywords else 'auto-discovered'}")
    lines.append("")

    headers = ["Time window", "Peak", "Baseline (median)", "Ratio", "Robust-z"]
    for metric in ("volume", "sentiment", "engagement", "topic"):
        if metric not in spikes:
            continue
        lines.append(f"## {metric.capitalize()}")
        lines.append("")
        metric_spikes = spikes[metric]
        if isinstance(metric_spikes, dict):
            rendered_any = False
            for term, term_spikes in metric_spikes.items():
                if not term_spikes:
                    continue
                rendered_any = True
                lines.append(f"### {term}")
                lines.append("")
                _append_spike_table(lines, headers, term_spikes)
                for spike in term_spikes:
                    for bullet in _metric_bullets(spike):
                        lines.append(f"- {bullet}")
                lines.append("")
            if not rendered_any:
                lines.append("No spikes detected.")
                lines.append("")
        else:
            if not metric_spikes:
                lines.append("No spikes detected.")
                lines.append("")
                continue
            _append_spike_table(lines, headers, metric_spikes)
            for spike in metric_spikes:
                for bullet in _metric_bullets(spike):
                    lines.append(f"- {bullet}")
            lines.append("")

    if top_spiking_topics:
        lines.append("## Top spiking topics")
        lines.append("")
        for entry in top_spiking_topics:
            spike = max(entry["spikes"], key=lambda s: s["robust_z"])
            ratio = f"{spike['ratio']:.1f}x" if spike["ratio"] is not None else "-"
            lines.append(f"- **{entry['term']}** — peak {_fmt_num(spike['value'])} at {spike['from_iso']} (baseline {_fmt_num(spike['median'])}, ratio {ratio}, robust-z {spike['robust_z']:.2f})")
            for sample in spike["sample_posts"][:1]:
                lines.append(f'  - "{sample["message"]}" — {sample["link"]}')
        lines.append("")

    lines.append("---")
    lines.append("Generated by lenx-spike-detector")
    return "\n".join(lines) + "\n"


def _render_text(args, meta: dict, series: dict, spikes: dict, top_spiking_topics: list[dict], topic_keywords: list[str]) -> str:
    lines = ["SPIKE DETECTION REPORT - TASK " + args.task_id]
    lines.append("=" * 40)
    lines.append(f"Time range: {meta['time_range_label']}")
    lines.append(f"Bucket: {meta['bucket']['bucket_label']} ({meta['bucket']['num_buckets']} buckets)")
    lines.append(f"Total records: {meta['total_records']}")
    lines.append(f"Sensitivity (robust z): {args.sensitivity}")
    lines.append(f"Metrics: {', '.join(sorted(meta['metrics_requested']))}")
    lines.append(f"Sentiment target: {args.sentiment}")
    lines.append(f"Topic filter: {', '.join(topic_keywords) if topic_keywords else 'auto-discovered'}")
    lines.append("")

    for metric in ("volume", "sentiment", "engagement", "topic"):
        if metric not in spikes:
            continue
        lines.append(metric.upper())
        lines.append("-" * 40)
        metric_spikes = spikes[metric]
        if isinstance(metric_spikes, dict):
            rendered_any = False
            for term, term_spikes in metric_spikes.items():
                if not term_spikes:
                    continue
                rendered_any = True
                lines.append(term.upper())
                for spike in term_spikes:
                    ratio = f"{spike['ratio']:.1f}x" if spike["ratio"] is not None else "-"
                    lines.append(f"* Time window {spike['from_iso']} - {spike['to_iso']}: peak {_fmt_num(spike['value'])}, baseline {_fmt_num(spike['median'])}, ratio {ratio}, robust-z {spike['robust_z']:.2f}")
                    for bullet in _metric_bullets(spike):
                        lines.append(f"  - {bullet}")
            if not rendered_any:
                lines.append("No spikes detected.")
                lines.append("")
        else:
            if not metric_spikes:
                lines.append("No spikes detected.")
                lines.append("")
                continue
            for spike in metric_spikes:
                ratio = f"{spike['ratio']:.1f}x" if spike["ratio"] is not None else "-"
                lines.append(f"* Time window {spike['from_iso']} - {spike['to_iso']}: peak {_fmt_num(spike['value'])}, baseline {_fmt_num(spike['median'])}, ratio {ratio}, robust-z {spike['robust_z']:.2f}")
                for bullet in _metric_bullets(spike):
                    lines.append(f"  - {bullet}")
        lines.append("")

    if top_spiking_topics:
        lines.append("TOP SPIKING TOPICS")
        lines.append("-" * 40)
        for entry in top_spiking_topics:
            spike = max(entry["spikes"], key=lambda s: s["robust_z"])
            ratio = f"{spike['ratio']:.1f}x" if spike["ratio"] is not None else "-"
            lines.append(f"* {entry['term']} - peak {_fmt_num(spike['value'])} at {spike['from_iso']} (baseline {_fmt_num(spike['median'])}, ratio {ratio}, robust-z {spike['robust_z']:.2f})")
            for sample in spike["sample_posts"][:1]:
                lines.append(f'  - "{sample["message"]}" ({sample["link"]})')
        lines.append("")

    lines.append("Generated by lenx-spike-detector")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Chart generation
# ---------------------------------------------------------------------------


def _generate_chart(args, from_ms: int, bucket_ms: int, num_buckets: int, series: dict, spikes: dict, topic_series: list[float] | None, top_term: str | None) -> bool:
    """Render the spike chart PNG. Returns True on success, False when skipped."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as e:
        print(f"Warning: matplotlib not available ({e}); skipping chart generation.", file=sys.stderr)
        return False

    metric_order = [m for m in ("volume", "sentiment", "engagement") if m in series]
    plot_metrics = metric_order if metric_order else ["volume"]
    num_plots = len(plot_metrics)
    fig, axes = plt.subplots(num_plots, 1, sharex=True, figsize=(12, 3.4 * num_plots))
    if num_plots == 1:
        axes = [axes]

    x = [datetime.fromtimestamp((from_ms + i * bucket_ms) / 1000) for i in range(num_buckets)]
    axes[0].set_title(f"Spike detection — Task {args.task_id}", fontsize=13, pad=12)
    if top_term:
        axes[0].text(0.99, 0.97, f"Top spiking term: {top_term}", transform=axes[0].transAxes,
                     ha="right", va="top", fontsize=9, style="italic")

    for ax, metric in zip(axes, plot_metrics):
        values = series.get(metric, [0] * num_buckets)
        if not values:
            continue
        ax.plot(x, values, color="tab:blue", linewidth=1.4)
        ax.set_ylabel(metric.capitalize(), fontsize=10)
        ax.grid(True, alpha=0.3)
        metric_spikes = spikes.get(metric, [])
        if isinstance(metric_spikes, dict):
            metric_spikes = [s for entries in metric_spikes.values() for s in entries]
        for spike in metric_spikes:
            idx = spike["bucket_index"]
            ax.plot(x[idx], spike["value"], "ro", markersize=7)
            ax.annotate(str(spike["value"]), (x[idx], spike["value"]),
                        textcoords="offset points", xytext=(0, 7), ha="center", fontsize=8)

    if topic_series and any(topic_series):
        ax2 = axes[0].twinx()
        ax2.plot(x, topic_series, color="tab:red", linestyle="--", linewidth=1.3, label="topic")
        ax2.set_ylabel("Topic", fontsize=10)
        ax2.legend(loc="upper left", fontsize=8)

    plt.xticks(rotation=45, ha="right")
    fig.tight_layout()
    os.makedirs(os.path.dirname(args.chart) or ".", exist_ok=True)
    fig.savefig(args.chart, dpi=120)
    plt.close(fig)
    return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Detect activity spikes in Lenx task data")
    parser.add_argument("--input", required=True, help="Path to input TSV (header line starts with '#')")
    parser.add_argument("--from-ms", required=True, type=int, help="Start of range in Unix milliseconds")
    parser.add_argument("--to-ms", required=True, type=int, help="End of range in Unix milliseconds")
    parser.add_argument("--task-id", required=True, help="Lenx task ID (for labels only)")
    parser.add_argument("--report", required=True, help="Base path for the report; .md or .txt appended per --format")
    parser.add_argument("--chart", default=None, help="Path to output PNG chart (skipped with --no-chart)")
    parser.add_argument("--metadata", required=True, help="Path to output metadata JSON")
    parser.add_argument("--metrics", default="all", help="Comma-list from volume,sentiment,engagement,topic (or 'all')")
    parser.add_argument("--sentiment", default="negative", choices=["negative", "positive", "neutral"],
                        help="Target sentiment for the sentiment metric")
    parser.add_argument("--sensitivity", type=float, default=3.0, help="Robust-z threshold for a spike")
    parser.add_argument("--bucket", default="auto", choices=["auto", "hourly", "6h", "daily"],
                        help="Bucket size; auto picks hourly (<=2d), 6h (<=7d), or daily")
    parser.add_argument("--max-topics", type=int, default=15, help="Max terms considered for topic auto-discovery")
    fmt_group = parser.add_mutually_exclusive_group()
    fmt_group.add_argument("--format", dest="format", default="markdown", choices=["markdown", "text"],
                           help="Report format")
    fmt_group.add_argument("--markdown", dest="format", action="store_const", const="markdown",
                           help="Alias for --format markdown")
    fmt_group.add_argument("--text", dest="format", action="store_const", const="text",
                           help="Alias for --format text")
    parser.add_argument("--topic", default=None, help="Comma-separated keywords to track (default: auto-discover)")
    parser.add_argument("--no-chart", action="store_true", help="Skip PNG chart generation")
    parser.add_argument("--stopwords", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "stopwords_en.txt"),
                        help="Stopword file for topic auto-discovery")
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"ERROR: Input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    raw_rows = _load_tsv(args.input)
    records = []
    for row in raw_rows:
        ts = _to_int(row.get("unix_timestamp"))
        if ts <= 0:
            continue
        records.append(
            {
                "ts": ts,
                "message": str(row.get("post_message", "")),
                "sentiment": str(row.get("ai_sentiment", "")).strip().lower(),
                "reaction": _to_int(row.get("reaction_count")),
                "comment": _to_int(row.get("comment_count")),
                "share": _to_int(row.get("share_count")),
                "views": _to_int(row.get("view_count")),
                "site": str(row.get("site", "")).strip(),
                "link": str(row.get("post_link", "")).strip(),
            }
        )

    range_ms = max(args.to_ms - args.from_ms, 1)
    bucket_mode = args.bucket
    if bucket_mode == "auto":
        if range_ms <= 172800000:
            bucket_mode = "hourly"
        elif range_ms <= 604800000:
            bucket_mode = "6h"
        else:
            bucket_mode = "daily"
    bucket_ms = BUCKET_MS[bucket_mode]
    num_buckets = max(1, math.ceil(range_ms / bucket_ms))

    valid_metrics = {"volume", "sentiment", "engagement", "topic"}
    requested = {m.strip().lower() for m in args.metrics.split(",") if m.strip()}
    if "all" in requested:
        requested = set(valid_metrics)
    else:
        invalid = requested - valid_metrics
        if invalid:
            print(f"ERROR: Unknown metrics: {', '.join(sorted(invalid))}. Valid: volume, sentiment, engagement, topic, all", file=sys.stderr)
            sys.exit(1)

    target_sentiment = args.sentiment.lower()
    topic_keywords = [k.strip().lower() for k in args.topic.split(",")] if args.topic else []
    topic_keywords = [k for k in topic_keywords if k]

    stopwords = _load_stopwords(args.stopwords)

    # -----------------------------------------------------------------------
    # Per-metric bucket aggregations
    # -----------------------------------------------------------------------
    metrics_data = {m: _new_metric(num_buckets) for m in requested}
    sentiment_buckets = [Counter() for _ in range(num_buckets)]
    topic_total = [0] * num_buckets

    tokens_by_record = None
    if "topic" in requested and not topic_keywords:
        tokens_by_record = [_clean_tokens(_tokenize(rec["message"]), stopwords) for rec in records]

    for rec in records:
        idx = _bucket_index(rec["ts"], args.from_ms, bucket_ms, num_buckets)
        sentiment_buckets[idx][rec["sentiment"] or "unknown"] += 1

        if "volume" in requested:
            metric = metrics_data["volume"]
            metric["series"][idx] += 1
            if rec["site"]:
                metric["sites"][idx][rec["site"]] += 1
            _add_sample(metric["samples"][idx], rec)

        if "sentiment" in requested:
            metric = metrics_data["sentiment"]
            if rec["sentiment"] == target_sentiment:
                metric["series"][idx] += 1
                if rec["site"]:
                    metric["sites"][idx][rec["site"]] += 1
                _add_sample(metric["samples"][idx], rec)

        if "engagement" in requested:
            metric = metrics_data["engagement"]
            eng = rec["reaction"] + rec["comment"] + rec["share"]
            metric["series"][idx] += eng
            if rec["site"]:
                metric["sites"][idx][rec["site"]] += 1
            if eng > 0:
                _add_sample(metric["samples"][idx], rec)

        if "topic" in requested and topic_keywords:
            message_lower = rec["message"].lower()
            if any(kw in message_lower for kw in topic_keywords):
                metric = metrics_data["topic"]
                metric["series"][idx] += 1
                if rec["site"]:
                    metric["sites"][idx][rec["site"]] += 1
                _add_sample(metric["samples"][idx], rec)

    # -----------------------------------------------------------------------
    # Topic auto-discovery (per-term series + spikes)
    # -----------------------------------------------------------------------
    term_series = {}
    term_spikes = {}
    term_samples = {}
    top_spiking_topics = []
    if tokens_by_record is not None:
        doc_freq = Counter()
        for tokens in tokens_by_record:
            for t in set(tokens):
                doc_freq[t] += 1
        top_terms = [t for t, _ in doc_freq.most_common(args.max_topics)]
        term_series = {t: [0] * num_buckets for t in top_terms}
        term_samples = {t: [[] for _ in range(num_buckets)] for t in top_terms}
        term_sites = {t: [Counter() for _ in range(num_buckets)] for t in top_terms}
        term_sentiment = {t: [Counter() for _ in range(num_buckets)] for t in top_terms}
        term_set = set(top_terms)
        for rec, tokens in zip(records, tokens_by_record):
            idx = _bucket_index(rec["ts"], args.from_ms, bucket_ms, num_buckets)
            for t in set(tokens):
                if t in term_set:
                    term_series[t][idx] += 1
                    if rec["site"]:
                        term_sites[t][idx][rec["site"]] += 1
                    term_sentiment[t][idx][rec["sentiment"] or "unknown"] += 1
                    _add_sample(term_samples[t][idx], rec)
        for term in top_terms:
            term_spikes[term] = [s for s in detect_spikes(term_series[term], args.sensitivity)]
            if term_spikes[term]:
                best = max(term_spikes[term], key=lambda s: s["robust_z"])
                top_spiking_topics.append(
                    {"term": term, "max_robust_z": best["robust_z"], "spikes": term_spikes[term]}
                )
        top_spiking_topics.sort(key=lambda e: e["max_robust_z"], reverse=True)
        top_spiking_topics = top_spiking_topics[:MAX_TOP_SPIKING_TOPICS]

    # -----------------------------------------------------------------------
    # Spike detection + enrichment
    # -----------------------------------------------------------------------
    spikes = {}
    for metric in requested:
        metric_spikes = detect_spikes(metrics_data[metric]["series"], args.sensitivity)
        for spike in metric_spikes:
            _enrich_spike(spike, metrics_data[metric], sentiment_buckets, args.from_ms, bucket_ms)
        spikes[metric] = metric_spikes

    if "topic" in requested and not topic_keywords:
        topic_spikes_out = {}
        for term, term_spike_list in term_spikes.items():
            if not term_spike_list:
                continue
            enriched = []
            for spike in term_spike_list:
                sample_metric = {"samples": term_samples[term], "sites": term_sites[term]}
                _enrich_spike(spike, sample_metric, sentiment_buckets, args.from_ms, bucket_ms, sentiment_override=term_sentiment[term])
                enriched.append(spike)
            topic_spikes_out[term] = enriched
        spikes["topic"] = topic_spikes_out

    # -----------------------------------------------------------------------
    # Metadata JSON
    # -----------------------------------------------------------------------
    series_out = {}
    for metric in requested:
        if metric == "topic" and not topic_keywords:
            series_out["topic"] = {t: series for t, series in term_series.items()}
        else:
            series_out[metric] = metrics_data[metric]["series"]
    if "sentiment" in requested:
        total = metrics_data["sentiment"]["series"]
        series_out["sentiment_share"] = [
            round(count / tot, 4) if tot > 0 else 0.0
            for count, tot in zip(total, [sum(sentiment_buckets[i].values()) for i in range(num_buckets)])
        ]
    if "engagement" in requested:
        series_out["views"] = [0] * num_buckets
        for rec in records:
            idx = _bucket_index(rec["ts"], args.from_ms, bucket_ms, num_buckets)
            series_out["views"][idx] += rec["views"]

    metadata = {
        "task_id": args.task_id,
        "from_ms": args.from_ms,
        "to_ms": args.to_ms,
        "time_range_label": f"{_fmt_time(args.from_ms)} -> {_fmt_time(args.to_ms)}",
        "total_records": len(records),
        "bucket": {
            "mode": bucket_mode,
            "bucket_ms": bucket_ms,
            "bucket_label": BUCKET_LABELS[bucket_mode],
            "num_buckets": num_buckets,
        },
        "sensitivity": args.sensitivity,
        "metrics_requested": sorted(requested),
        "sentiment_target": target_sentiment,
        "topic": topic_keywords if topic_keywords else None,
        "buckets": [
            {
                "start_ts": args.from_ms + i * bucket_ms,
                "end_ts": args.from_ms + (i + 1) * bucket_ms,
                "iso": _fmt_time(args.from_ms + i * bucket_ms),
            }
            for i in range(num_buckets)
        ],
        "series": series_out,
        "spikes": spikes,
        "top_spiking_topics": [
            {
                "term": entry["term"],
                "max_robust_z": entry["max_robust_z"],
                "spikes": term_spikes[entry["term"]],
            }
            for entry in top_spiking_topics
        ],
    }

    os.makedirs(os.path.dirname(args.metadata) or ".", exist_ok=True)
    with open(args.metadata, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    # -----------------------------------------------------------------------
    # Report
    # -----------------------------------------------------------------------
    report_ext = ".md" if args.format == "markdown" else ".txt"
    report_path = args.report + report_ext
    if len(records) == 0:
        report_body = "No data found for task {0} in the given time range.\n\nGenerated by lenx-spike-detector\n".format(args.task_id)
    elif args.format == "markdown":
        report_body = _render_markdown(args, metadata, series_out, spikes, top_spiking_topics, topic_keywords)
    else:
        report_body = _render_text(args, metadata, series_out, spikes, top_spiking_topics, topic_keywords)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_body)

    # -----------------------------------------------------------------------
    # Chart
    # -----------------------------------------------------------------------
    chart_written = False
    if len(records) > 0 and args.chart and not args.no_chart:
        topic_series = series_out.get("topic") if isinstance(series_out.get("topic"), list) else None
        top_term = top_spiking_topics[0]["term"] if top_spiking_topics else None
        chart_written = _generate_chart(args, args.from_ms, bucket_ms, num_buckets, series_out, spikes, topic_series, top_term)

    # -----------------------------------------------------------------------
    # Summary
    # -----------------------------------------------------------------------
    spike_counts = {m: len(spikes.get(m, [])) for m in ("volume", "sentiment", "engagement")}
    topic_count = 0
    if "topic" in spikes:
        topic_spikes = spikes["topic"]
        if isinstance(topic_spikes, dict):
            topic_count = sum(len(entries) for entries in topic_spikes.values())
        else:
            topic_count = len(topic_spikes)
    spike_counts["topic"] = topic_count
    written_note = "Wrote report, chart, metadata." if chart_written else "Wrote report and metadata."
    print(
        written_note + " Spikes: "
        f"volume={spike_counts['volume']} sentiment={spike_counts['sentiment']} "
        f"engagement={spike_counts['engagement']} topic={spike_counts['topic']}"
    )
    print(f"Report: {report_path}")
    print(f"Metadata: {args.metadata}")
    if args.chart:
        print(f"Chart: {args.chart if chart_written else 'skipped (matplotlib unavailable or --no-chart)'}")


if __name__ == "__main__":
    main()
