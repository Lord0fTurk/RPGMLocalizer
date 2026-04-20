#!/usr/bin/env python3
"""
Proper Benchmarking: Code-Level Validation
Tests if RPG Maker CODES are correctly restored (case-insensitive for text)
"""
import sys
import time
import re
from pathlib import Path
from typing import Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.syntax_guard_rpgm import (
    protect_for_translation,
    restore_from_translation,
    validate_translation_integrity,
    inject_missing_placeholders
)
from src.utils.html_shield import HTMLShield

# Test data with clear code markers
TEST_SAMPLES = [
    "\\c[3]Red Text\\c[0]",
    "\\i[32] Legendary Sword",
    "\\p[1] will join your party",
    "\\c[1]Warning:\\c[0] \\i[52]Poison!",
    "[sad]The hero mourns[/sad]",
    "<WordWrap>Long message text wraps here</WordWrap>",
]

# Extract codes from text
def extract_codes(text: str) -> set:
    """Extract all RPG Maker codes from text"""
    codes = set()
    # Backslash codes
    codes.update(re.findall(r'\\[a-zA-Z]\[\d+\]', text))
    codes.update(re.findall(r'\\[a-zA-Z]\[[^\]]+\]', text))
    # Bracket tags
    codes.update(re.findall(r'\[[a-zA-Z0-9_/]+\]', text))
    # HTML tags
    codes.update(re.findall(r'<\w+>', text))
    codes.update(re.findall(r'</\w+>', text))
    return codes


def validate_code_restoration(original: str, restored: str) -> Tuple[bool, Dict]:
    """
    Validate that all codes from original appear in restored
    Returns (success: bool, details: dict)
    """
    original_codes = extract_codes(original)
    restored_codes = extract_codes(restored)
    
    missing = original_codes - restored_codes
    extra = restored_codes - original_codes
    
    success = len(missing) == 0
    
    return success, {
        'original_codes': original_codes,
        'restored_codes': restored_codes,
        'missing': missing,
        'extra': extra,
    }


class BenchmarkResult:
    def __init__(self, name: str):
        self.name = name
        self.perfect_restorations = 0
        self.code_restorations_ok = 0
        self.total_samples = 0
        self.total_time = 0.0
        self.errors = []
        
    def add_result(self, perfect: bool, codes_ok: bool, elapsed: float, error: str | None = None):
        if perfect:
            self.perfect_restorations += 1
        if codes_ok:
            self.code_restorations_ok += 1
        self.total_samples += 1
        self.total_time += elapsed
        if error:
            self.errors.append(error)
        
    def perfect_rate(self) -> float:
        if self.total_samples == 0:
            return 0.0
        return (self.perfect_restorations / self.total_samples) * 100
    
    def code_rate(self) -> float:
        if self.total_samples == 0:
            return 0.0
        return (self.code_restorations_ok / self.total_samples) * 100
    
    def avg_time(self) -> float:
        if self.total_samples == 0:
            return 0.0
        return (self.total_time / self.total_samples) * 1000  # ms
    
    def __str__(self) -> str:
        return f"""
╭─ {self.name}
│  Perfect Match: {self.perfect_rate():.1f}% ({self.perfect_restorations}/{self.total_samples})
│  Code Restoration OK: {self.code_rate():.1f}% ({self.code_restorations_ok}/{self.total_samples})
│  Avg Time/Sample: {self.avg_time():.2f}ms
│  Total Time: {self.total_time:.3f}s
│  Errors: {len(self.errors)}
╰─
"""


def benchmark_htmlshield():
    """Benchmark v0.6.5 HTMLShield"""
    result = BenchmarkResult("v0.6.5 (HTMLShield)")
    shield = HTMLShield()
    
    for sample in TEST_SAMPLES:
        try:
            start = time.perf_counter()
            
            protected, token_map = shield.shield_with_map(sample)
            translated = protected.lower()
            restored = shield.unshield_with_map(translated, token_map)
            
            elapsed = time.perf_counter() - start
            
            perfect = restored.lower() == sample.lower()
            codes_ok, _ = validate_code_restoration(sample, restored)
            
            result.add_result(perfect, codes_ok, elapsed)
            
        except Exception as e:
            result.add_result(False, False, 0, str(e))
    
    return result


def benchmark_syntax_guard():
    """Benchmark v0.6.6-beta syntax_guard_rpgm"""
    result = BenchmarkResult("v0.6.6-beta (syntax_guard_rpgm)")
    
    for sample in TEST_SAMPLES:
        try:
            start = time.perf_counter()
            
            protected, metadata = protect_for_translation(sample, use_html=False)
            translated = protected.lower()  # Simulate Google lowercase
            restored = restore_from_translation(translated, metadata, use_html=False)
            
            missing = validate_translation_integrity(restored, metadata)
            if missing:
                restored = inject_missing_placeholders(restored, translated, metadata, missing)
            
            elapsed = time.perf_counter() - start
            
            perfect = restored == sample
            codes_ok, _ = validate_code_restoration(sample, restored)
            
            result.add_result(perfect, codes_ok, elapsed)
            
        except Exception as e:
            result.add_result(False, False, 0, str(e))
    
    return result


def run_benchmarks():
    """Run full benchmark"""
    print("\n" + "=" * 70)
    print("BENCHMARKING: Code-Level Restoration Validation")
    print("=" * 70)
    print(f"\nTest Samples: {len(TEST_SAMPLES)}")
    print(f"Total Codes: {sum(len(extract_codes(s)) for s in TEST_SAMPLES)}")
    
    print("\n[*] Running v0.6.5 (HTMLShield)...")
    result_v65 = benchmark_htmlshield()
    
    print("[*] Running v0.6.6-beta (syntax_guard_rpgm)...")
    result_v66 = benchmark_syntax_guard()
    
    print("\n" + "=" * 70)
    print("RESULTS")
    print("=" * 70)
    
    print(result_v65)
    print(result_v66)
    
    # Comparison
    code_improvement = result_v66.code_rate() - result_v65.code_rate()
    perfect_improvement = result_v66.perfect_rate() - result_v65.perfect_rate()
    overhead = ((result_v66.avg_time() - result_v65.avg_time()) / result_v65.avg_time() * 100) if result_v65.avg_time() > 0 else 0
    
    print("╭─ COMPARISON (Code-Level)")
    print(f"│  Code Restoration: {code_improvement:+.1f}% (v0.6.5: {result_v65.code_rate():.1f}% → v0.6.6-beta: {result_v66.code_rate():.1f}%)")
    print(f"│  Perfect Match: {perfect_improvement:+.1f}% (v0.6.5: {result_v65.perfect_rate():.1f}% → v0.6.6-beta: {result_v66.perfect_rate():.1f}%)")
    print(f"│  Speed: {overhead:+.1f}% overhead")
    print("╰─")
    
    print("\n" + "=" * 70)
    print("NOTE: Perfect Match reflects case changes from translation.")
    print("Code Restoration is what matters for game engine safety.")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    run_benchmarks()
