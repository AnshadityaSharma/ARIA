from scripts.phase3_benchmark import measure


def test_phase3_benchmark_contract():
    report = measure(iterations=100, startup_iterations=1)
    required = {
        "normalization", "grammar_direct", "grammar_paraphrase", "grammar_hinglish",
        "parameter_numeric_conversion", "parameter_command_parse", "state_reference_resolution",
        "application_exact_resolution", "application_compact_resolution",
        "application_typo_resolution", "full_interpretation_direct",
        "full_interpretation_paraphrase", "full_interpretation_hinglish",
        "clarification", "abstention", "fresh_process_startup_and_interpretation",
    }
    assert required == set(report["timing_ms"])
    assert report["sample_counts"] == {"warm": 100, "startup": 1, "cold": 1}
    assert report["resources"]["process_count"] == 1
    assert report["objectives_ms"]["status"].startswith("proposed")
