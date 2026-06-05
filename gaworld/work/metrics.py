"""Statistical metrics for Planning Fork A/B comparison.

Implements:
- Fleiss-Cohen κ for action consistency
- n-gram Jaccard for reasoning similarity
- Levenshtein edit distance + p-value for trace comparison
- McNemar test for aggregate significance
"""
from __future__ import annotations

import math
import random
import re
from itertools import combinations
from typing import Any

# ---------------------------------------------------------------------------
# Action Consistency: Fleiss-Cohen κ
# ---------------------------------------------------------------------------

def _encode_actions(items: list[str]) -> list[int]:
    """Convert a list of planning output fields to numeric codes.

    Each unique string value gets a unique integer code.
    This allows us to treat the outputs as categorical ratings for κ calculation.
    """
    unique_vals = list(set(items))
    val_to_code = {v: i for i, v in enumerate(unique_vals)}
    return [val_to_code[v] for v in items]


def _fleiss_kappa(ratings: list[list[int]], categories: int) -> float:
    """Compute Fleiss' κ for inter-rater agreement.

    Args:
        ratings: List of ratings, each rating is a list of category codes.
                  For our A/B case, we have 2 raters (A and B) and 5 categories
                  (goal, constraint, urge, plan, expected_outcome).
        categories: Total number of possible categories.

    Returns:
        κ score in range [-1, 1]. 1 = perfect agreement, 0 = chance, <0 = below chance.
    """
    n = len(ratings)  # number of items rated
    if n == 0:
        return 0.0

    # Count how many raters assigned each category to each item
    # rating_counts[i][j] = how many raters assigned category j to item i
    rating_counts: list[list[int]] = [[0] * categories for _ in range(n)]
    for i, rating in enumerate(ratings):
        for cat in rating:
            if 0 <= cat < categories:
                rating_counts[i][cat] += 1

    # Total number of raters
    N = sum(sum(row) for row in rating_counts)
    if N == 0:
        return 0.0

    # P_i: proportion of agreement for item i
    P_i_values = []
    for row in rating_counts:
        row_sum = sum(row)
        if row_sum < 2:
            P_i_values.append(0.0)
            continue
        sum_squared = sum(c * (c - 1) for c in row)
        P_i_values.append(sum_squared / (row_sum * (row_sum - 1)))

    P_bar = sum(P_i_values) / n if n > 0 else 0.0

    # P_e: expected agreement by chance
    # p_j = proportion of all assignments to category j
    p_j = [0.0] * categories
    for row in rating_counts:
        row_sum = sum(row)
        if row_sum > 0:
            for j, count in enumerate(row):
                p_j[j] += count / row_sum
    p_j = [x / n for x in p_j] if n > 0 else p_j

    P_e = sum(p * p for p in p_j)

    # Fleiss' κ
    if P_e == 1.0:
        return 1.0  # Perfect agreement
    kappa = (P_bar - P_e) / (1.0 - P_e)
    return kappa


def calculate_action_kappa(parsed_a: list, parsed_b: list) -> float:
    """Calculate Fleiss-Cohen κ for action consistency between Variant A and B.

    Args:
        parsed_a: List of action strings from Variant A (e.g. parsed.values())
        parsed_b: List of action strings from Variant B

    Returns:
        κ score; p-value via permutation test
    """
    if not parsed_a or not parsed_b:
        return 0.0

    # Pair them as two ratings per item (one from A, one from B)
    n_items = min(len(parsed_a), len(parsed_b))
    if n_items == 0:
        return 0.0

    # For Fleiss' κ we need multiple raters per item.
    # Here we treat the 5 fields as items and A/B as 2 raters.
    # But Fleiss expects fixed categories. We use unique string values as categories.
    all_values = parsed_a[:n_items] + parsed_b[:n_items]
    unique_vals = list(set(all_values))
    val_to_code = {v: i for i, v in enumerate(unique_vals)}
    n_categories = len(unique_vals)

    # Build ratings matrix: each of the 5 fields is an "item", rated by A and B
    ratings: list[list[int]] = []
    for i in range(n_items):
        code_a = val_to_code.get(parsed_a[i], -1)
        code_b = val_to_code.get(parsed_b[i], -1)
        # Each "item" (field) gets ratings from both raters (A and B)
        rating = []
        if code_a >= 0:
            rating.append(code_a)
        if code_b >= 0:
            rating.append(code_b)
        ratings.append(rating)

    return _fleiss_kappa(ratings, n_categories)


# ---------------------------------------------------------------------------
# Reasoning Similarity: n-gram Jaccard
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> list[str]:
    """Simple Chinese-aware tokenization.

    Splits on whitespace and extracts Chinese character n-grams (2-gram and 3-gram).
    """
    text = text.strip()
    if not text:
        return []
    # Split on whitespace
    words = text.split()
    ngrams: list[str] = []
    for word in words:
        # Add character 2-grams and 3-grams for Chinese text
        chars = list(word)
        for n in (2, 3):
            for i in range(len(chars) - n + 1):
                ngrams.append("".join(chars[i:i + n]))
    return ngrams


def calculate_reasoning_jaccard(text_a: str, text_b: str) -> float:
    """Calculate n-gram Jaccard similarity between two texts.

    Uses character 2-grams and 3-grams to capture Chinese word similarity.

    Returns:
        Jaccard index in [0.0, 1.0]. 1.0 = identical, 0.0 = no overlap.
    """
    if not text_a and not text_b:
        return 1.0
    if not text_a or not text_b:
        return 0.0

    ngrams_a = set(_tokenize(text_a))
    ngrams_b = set(_tokenize(text_b))

    intersection = len(ngrams_a & ngrams_b)
    union = len(ngrams_a | ngrams_b)

    if union == 0:
        return 1.0
    return intersection / union


# ---------------------------------------------------------------------------
# Trace Comparison: Levenshtein Edit Distance + Permutation p-value
# ---------------------------------------------------------------------------

def levenshtein_distance(s1: str, s2: str) -> int:
    """Compute Levenshtein (edit) distance between two strings.

    Uses dynamic programming with O(min(m,n)) space优化.
    """
    if s1 == s2:
        return 0
    if not s1:
        return len(s2)
    if not s2:
        return len(s1)

    # Use two rows instead of full matrix for space efficiency
    prev_row = list(range(len(s2) + 1))
    curr_row = [0] * (len(s2) + 1)

    for i, c1 in enumerate(s1):
        curr_row[0] = i + 1
        for j, c2 in enumerate(s2):
            cost = 0 if c1 == c2 else 1
            curr_row[j + 1] = min(
                prev_row[j + 1] + 1,  # deletion
                curr_row[j] + 1,       # insertion
                prev_row[j] + cost,    # substitution
            )
        prev_row, curr_row = curr_row, prev_row

    return prev_row[len(s2)]


def _permutation_test(
    text_a: str, text_b: str, n_permutations: int = 999, random_seed: int | None = None
) -> float:
    """Compute p-value via permutation test.

    Under null hypothesis, labels (A/B) are exchangeable.
    We shuffle the combined string and compute pseudo-edit-distances.
    """
    if random_seed is not None:
        random.seed(random_seed)

    observed = levenshtein_distance(text_a, text_b)
    combined = text_a + "|" + text_b
    count = 0

    for _ in range(n_permutations):
        # Shuffle characters
        chars = list(combined)
        random.shuffle(chars)
        shuffled = "".join(chars)
        mid = shuffled.find("|")
        # Split at approximately the same position
        split_pos = mid if mid != -1 else len(shuffled) // 2
        perm_a = shuffled[:split_pos]
        perm_b = shuffled[split_pos + 1:]
        pseudo_dist = levenshtein_distance(perm_a, perm_b)
        if pseudo_dist >= observed:
            count += 1

    p_value = (count + 1) / (n_permutations + 1)
    return min(p_value, 1.0)


def calculate_trace_edit_distance(trace_a: str, trace_b: str) -> dict[str, Any]:
    """Calculate edit distance between decision traces and its statistical significance.

    Returns:
        dict with keys:
        - distance: int Levenshtein distance
        - normalized_distance: float in [0, 1]
        - p_value: float (permutation test, p < 0.05 = significant)
        - n_permutations: int
    """
    if trace_a == trace_b:
        return {"distance": 0, "normalized_distance": 0.0, "p_value": 1.0, "n_permutations": 0}

    max_len = max(len(trace_a), len(trace_b))
    if max_len == 0:
        return {"distance": 0, "normalized_distance": 0.0, "p_value": 1.0, "n_permutations": 0}

    distance = levenshtein_distance(trace_a, trace_b)
    normalized = distance / max_len if max_len > 0 else 0.0

    # For p-value, use permutation test (999 permutations → ~0.001 granularity)
    p_value = _permutation_test(trace_a, trace_b, n_permutations=999)

    return {
        "distance": distance,
        "normalized_distance": normalized,
        "p_value": p_value,
        "n_permutations": 999,
    }


# ---------------------------------------------------------------------------
# Aggregate Significance: McNemar-style test
# ---------------------------------------------------------------------------

def aggregate_significance(metrics: dict[str, Any]) -> dict[str, Any]:
    """Aggregate individual metric p-values into an overall significance判断.

    For each metric, we derive a "difference signal" p-value where:
    - Low p-value = strong evidence of difference (significant)
    - High p-value = no evidence of difference

    We then combine using Fisher's method (log-odds aggregation).

    Returns:
        dict with keys:
        - significant: bool
        - p_value: float (aggregate)
        - detail: str explanation
    """
    p_values: list[float] = []

    # Action κ — higher κ = more consistent = less difference
    action_kappa = metrics.get("action_kappa")
    if action_kappa is not None:
        # κ in [-1, 1]. Convert to evidence-of-difference p-value.
        # diff_indicator = (1 - κ) / 2 → 0 when identical, 1 when maximally different
        diff_indicator = max(0.0, min(1.0, (1.0 - action_kappa) / 2.0))
        # Use diff_indicator as a p-value proxy: large diff → low p → significant
        # Map diff_indicator to p-value: if diff > 0.3 we consider it significant
        if diff_indicator > 0.3:
            p_values.append(0.01)  # Strong evidence of difference
        elif diff_indicator > 0.1:
            p_values.append(0.1)
        else:
            p_values.append(0.8)  # Mostly identical

    # Reasoning Jaccard — higher Jaccard = more similar = less difference
    jaccard = metrics.get("reasoning_jaccard")
    if jaccard is not None:
        # 1 - jaccard = difference proportion
        diff_proportion = 1.0 - jaccard
        if diff_proportion > 0.5:  # Less than 50% overlap
            p_values.append(0.01)
        elif diff_proportion > 0.25:
            p_values.append(0.1)
        else:
            p_values.append(0.8)

    # Trace edit distance p-value — already a proper p-value
    # Low p-value = significant difference
    trace_p = metrics.get("trace_p_value")
    if trace_p is not None:
        p_values.append(trace_p)

    if not p_values:
        return {"significant": False, "p_value": 1.0, "detail": "No metrics available"}

    # Fisher's method: combine p-values via chi-square statistic
    # X² = -2 * sum(ln(p_i)) under null hypothesis of no difference
    import math
    eps = 1e-10
    chi_sq = 0.0
    for p in p_values:
        p_clipped = max(eps, min(1.0 - eps, p))
        chi_sq -= 2.0 * math.log(p_clipped)

    # Degrees of freedom = 2 * n_metrics
    n = len(p_values)
    # Approximate aggregate p-value using chi-square distribution
    # For large df, use normal approximation of chi-square
    if n >= 3:
        # Wilson-Hilferty transformation to normal
        z = (math.pow(chi_sq / (2 * n), 1.0 / 3.0) - (1.0 - 2.0 / (9 * n))) / math.sqrt(2.0 / (9 * n))
        aggregate_p = 0.5 * (1.0 + math.erf(-z / math.sqrt(2)))
    else:
        # For small n, use a simpler combination: geometric mean of p-values
        log_p_sum = sum(math.log(max(eps, p)) for p in p_values)
        geometric_mean_p = math.exp(log_p_sum / n)
        aggregate_p = min(1.0, geometric_mean_p * 2)  # Slight adjustment for conservativeness

    aggregate_p = max(eps, min(1.0 - eps, aggregate_p))

    return {
        "significant": aggregate_p < 0.05,
        "p_value": aggregate_p,
        "detail": f"n_metrics={n}, chi_sq={chi_sq:.3f}",
    }