"""
URL canonicalization and cross-provider source deduplication utilities.
"""

from typing import List, Dict, Any, Set
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode
import re
from app.services.search.base import NormalizedSource

# Common tracking / analytics query parameters to strip for clean canonicalization
TRACKING_PARAMS: Set[str] = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "utm_id",
    "ref",
    "ref_src",
    "fbclid",
    "gclid",
    "msclkid",
    "twclid",
    "trk",
    "mc_cid",
    "mc_eid",
    "_ga",
    "_gl",
    "spm",
}


def canonicalize_url(url: str) -> str:
    """
    Normalizes a URL to a canonical representation for deduplication.
    - Ensures scheme is present (defaults to https).
    - Lowercases scheme and netloc.
    - Strips default ports (:80, :443).
    - Normalizes path (collapses consecutive slashes, strips trailing slash unless root).
    - Removes fragments (#...).
    - Filters out tracking query parameters and sorts remaining query parameters.
    """
    if not url or not isinstance(url, str):
        return ""

    url_str = url.strip()
    if not url_str.startswith(("http://", "https://")):
        url_str = "https://" + url_str

    try:
        parsed = urlparse(url_str)
    except Exception:
        return url_str.lower().rstrip("/")

    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()

    # Strip default ports
    if scheme == "http" and netloc.endswith(":80"):
        netloc = netloc[:-3]
    elif scheme == "https" and netloc.endswith(":443"):
        netloc = netloc[:-4]

    # Strip www. prefix for consistent matching if desired, but keep hostname intact
    # Normalize path
    path = parsed.path
    if not path:
        path = "/"
    else:
        # Collapse multiple slashes
        path = re.sub(r"/+", "/", path)
        if len(path) > 1 and path.endswith("/"):
            path = path[:-1]

    # Filter tracking query parameters
    query_params = []
    if parsed.query:
        for key, val in parse_qsl(parsed.query, keep_blank_values=False):
            if key.lower() not in TRACKING_PARAMS:
                query_params.append((key, val))
        query_params.sort(key=lambda x: x[0])

    normalized_query = urlencode(query_params) if query_params else ""

    # Reconstruct canonical URL without fragment
    return urlunparse((scheme, netloc, path, "", normalized_query, ""))


def merge_and_deduplicate_sources(
    sources: List[NormalizedSource],
    max_total_results: int = 15
) -> List[NormalizedSource]:
    """
    Combines sources and deduplicates based on canonical URLs.
    When a URL appears in multiple providers:
    - Combines provider attributions into a unified sorted list (e.g. ['tavily', 'user_url']).
    - Keeps the richest title and longest snippet.
    - Retains maximum confidence score if available.
    - Merges provider-specific metadata.
    - Enforces max_total_results cap.
    """
    merged_map: Dict[str, NormalizedSource] = {}

    for src in sources:
        c_url = src.canonical_url or canonicalize_url(src.url)
        if not c_url:
            continue

        if c_url not in merged_map:
            # Create a clean copy
            providers = sorted(list(set(src.providers))) if src.providers else ["unknown"]
            merged_map[c_url] = NormalizedSource(
                url=src.url,
                canonical_url=c_url,
                title=src.title or "Untitled Source",
                snippet=src.snippet or "",
                score=src.score,
                providers=providers,
                metadata=dict(src.metadata)
            )
        else:
            existing = merged_map[c_url]
            # Merge provider attribution
            combined_providers = set(existing.providers)
            combined_providers.update(src.providers or [])
            existing.providers = sorted(list(combined_providers))

            # Pick better / longer title if existing is generic or shorter
            if src.title and (existing.title == "Untitled Source" or len(src.title) > len(existing.title)):
                existing.title = src.title

            # Pick longer snippet
            if src.snippet and len(src.snippet) > len(existing.snippet):
                existing.snippet = src.snippet

            # Retain highest score
            if src.score is not None:
                if existing.score is None or src.score > existing.score:
                    existing.score = src.score

            # Merge metadata
            if src.metadata:
                for k, v in src.metadata.items():
                    if k not in existing.metadata:
                        existing.metadata[k] = v
                    elif isinstance(existing.metadata[k], dict) and isinstance(v, dict):
                        existing.metadata[k].update(v)

    results = list(merged_map.values())
    return results[:max_total_results]
