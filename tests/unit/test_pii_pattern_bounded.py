"""Regression: the S-2 worker-PII patterns stay linear-time on long input (ReDoS guard)."""

import time

from src.services.service import has_worker_pii


def test_email_still_detected():
    assert has_worker_pii("worker email reviewer@example.com in payload")
    assert has_worker_pii("contact: a.b+c@mail.store.example.co.jp")


def test_non_pii_text_not_flagged():
    assert not has_worker_pii("store 12 night shift coverage below minimum")


def test_long_input_scans_quickly():
    # 50,000 chars is the S-1 input-size ceiling; an unbounded `+` before `@`
    # makes this search quadratic (seconds), a bounded one keeps it linear.
    text = "a" * 50_000
    start = time.perf_counter()
    assert not has_worker_pii(text)
    assert time.perf_counter() - start < 1.0
