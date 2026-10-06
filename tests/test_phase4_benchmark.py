from scripts.phase4_filesystem_benchmark import measure


def test_phase4_benchmark_contract():
    report = measure(iterations=10, large_iterations=3)
    assert {"4_kib", "1_mib", "8_mib", "directory_25_entries"} == set(report["hashing_and_manifest_scaling_ms"])
    assert report["hashing_and_manifest_scaling_ms"]["1_mib"]["bytes"] == 1024 * 1024
    assert report["resources"]["process_count"] == 1
    assert report["sample_counts"] == {"standard": 10, "large_content": 3, "startup": 10}
