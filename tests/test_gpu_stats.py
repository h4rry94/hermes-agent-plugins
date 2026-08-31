"""Unit tests for gpu-monitor's nvidia-smi sampling and formatting.

Run from the repository root:

    python -m unittest discover -s tests

Stdlib only, deliberately. The plugin's Python half has no dependencies, and
adding pytest here would mean a dependency install in CI to test code that
needs none.

`gpu_stats.py` is loaded by PATH rather than imported: the plugin folder is
`gpu-monitor`, which is not a valid module name, and `gpu-monitor/__init__.py`
reaches for a Hermes `ctx` this test has no business constructing. The module
under test imports nothing but the stdlib, so loading the single file is both
sufficient and honest about what is covered.

These tests live at the repo root, not inside the plugin: `hermes plugins
install` copies a plugin folder verbatim, so a `gpu-monitor/tests/` would ship
to everyone who installs the chip.
"""

import importlib.util
import subprocess
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = ROOT / "gpu-monitor" / "gpu_stats.py"


def _load_gpu_stats():
    spec = importlib.util.spec_from_file_location("gpu_stats", MODULE_PATH)
    if spec is None or spec.loader is None:  # pragma: no cover - import plumbing
        raise RuntimeError(f"cannot load {MODULE_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gpu_stats = _load_gpu_stats()


def _completed(stdout="", stderr="", returncode=0):
    return subprocess.CompletedProcess(args=["nvidia-smi"], returncode=returncode,
                                       stdout=stdout, stderr=stderr)


class ParseOutputTests(unittest.TestCase):
    """_parse_output turns raw CSV into normalized samples."""

    def test_single_gpu(self):
        sample = gpu_stats._parse_output("42, 8192, 24564, NVIDIA GeForce RTX 4090\n")
        self.assertEqual(
            sample,
            {
                "ok": True,
                "gpus": [
                    {
                        "util": 42,
                        "memUsed": 8192,
                        "memTotal": 24564,
                        "name": "NVIDIA GeForce RTX 4090",
                    }
                ],
            },
        )

    def test_multiple_gpus_keep_order(self):
        output = "10, 1024, 8192, GPU Zero\n90, 7000, 8192, GPU One\n"
        sample = gpu_stats._parse_output(output)
        self.assertTrue(sample["ok"])
        self.assertEqual([g["name"] for g in sample["gpus"]], ["GPU Zero", "GPU One"])
        self.assertEqual([g["util"] for g in sample["gpus"]], [10, 90])

    def test_name_containing_a_comma_is_rejoined(self):
        # The query is comma-separated and the name field is last, so a comma in
        # the model name splits into extra parts that have to be put back.
        sample = gpu_stats._parse_output("5, 100, 200, NVIDIA RTX 4090, Founders Edition")
        self.assertEqual(sample["gpus"][0]["name"], "NVIDIA RTX 4090, Founders Edition")

    def test_short_row_is_skipped(self):
        sample = gpu_stats._parse_output("42, 8192, 24564\n7, 100, 200, Good GPU")
        self.assertTrue(sample["ok"])
        self.assertEqual(len(sample["gpus"]), 1)
        self.assertEqual(sample["gpus"][0]["name"], "Good GPU")

    def test_non_numeric_row_is_skipped(self):
        sample = gpu_stats._parse_output("[N/A], [N/A], [N/A], Broken GPU\n7, 100, 200, Good GPU")
        self.assertTrue(sample["ok"])
        self.assertEqual(len(sample["gpus"]), 1)
        self.assertEqual(sample["gpus"][0]["name"], "Good GPU")

    def test_all_rows_unparseable_is_an_error(self):
        sample = gpu_stats._parse_output("[N/A], [N/A], [N/A], Broken GPU")
        self.assertFalse(sample["ok"])
        self.assertIn("unparseable nvidia-smi output", sample["error"])

    def test_empty_output_is_an_error(self):
        sample = gpu_stats._parse_output("   \n  ")
        self.assertFalse(sample["ok"])
        self.assertIn("unparseable", sample["error"])

    def test_blank_lines_between_rows_are_ignored(self):
        sample = gpu_stats._parse_output("10, 1, 2, A\n\n20, 3, 4, B\n")
        self.assertEqual(len(sample["gpus"]), 2)


class ReadGpusTests(unittest.TestCase):
    """read_gpus normalizes every failure into {"ok": False, "error": str}."""

    def test_missing_nvidia_smi(self):
        with mock.patch("shutil.which", return_value=None):
            sample = gpu_stats.read_gpus()
        self.assertEqual(sample, {"ok": False, "error": "nvidia-smi not found on PATH"})

    def test_timeout(self):
        with mock.patch("shutil.which", return_value="/usr/bin/nvidia-smi"), mock.patch(
            "subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="nvidia-smi", timeout=5)
        ):
            sample = gpu_stats.read_gpus()
        self.assertEqual(sample, {"ok": False, "error": "nvidia-smi timed out"})

    def test_permission_error_is_reported_not_raised(self):
        # which() can find an nvidia-smi that still cannot be executed. The
        # error has to come back as a sample: it escapes into /gpu and the
        # /stats endpoint otherwise.
        with mock.patch("shutil.which", return_value="/usr/bin/nvidia-smi"), mock.patch(
            "subprocess.run", side_effect=PermissionError(13, "Permission denied")
        ):
            sample = gpu_stats.read_gpus()
        self.assertEqual(
            sample,
            {"ok": False, "error": "could not run nvidia-smi: Permission denied"},
        )

    def test_os_error_without_strerror_still_reports(self):
        with mock.patch("shutil.which", return_value="/usr/bin/nvidia-smi"), mock.patch(
            "subprocess.run", side_effect=OSError("exec format error")
        ):
            sample = gpu_stats.read_gpus()
        self.assertEqual(
            sample,
            {"ok": False, "error": "could not run nvidia-smi: exec format error"},
        )

    def test_non_zero_exit_prefers_stderr(self):
        with mock.patch("shutil.which", return_value="/usr/bin/nvidia-smi"), mock.patch(
            "subprocess.run",
            return_value=_completed(stdout="ignored", stderr="  driver mismatch  ", returncode=9),
        ):
            sample = gpu_stats.read_gpus()
        self.assertEqual(sample, {"ok": False, "error": "driver mismatch"})

    def test_non_zero_exit_falls_back_to_stdout(self):
        with mock.patch("shutil.which", return_value="/usr/bin/nvidia-smi"), mock.patch(
            "subprocess.run",
            return_value=_completed(stdout="something on stdout", stderr="", returncode=1),
        ):
            sample = gpu_stats.read_gpus()
        self.assertEqual(sample, {"ok": False, "error": "something on stdout"})

    def test_non_zero_exit_with_no_output_still_reports(self):
        # An empty message would render as "GPU Monitor: " with nothing after it.
        with mock.patch("shutil.which", return_value="/usr/bin/nvidia-smi"), mock.patch(
            "subprocess.run", return_value=_completed(stdout="  ", stderr="", returncode=1)
        ):
            sample = gpu_stats.read_gpus()
        self.assertEqual(sample, {"ok": False, "error": "nvidia-smi failed"})

    def test_success_parses_stdout(self):
        with mock.patch("shutil.which", return_value="/usr/bin/nvidia-smi"), mock.patch(
            "subprocess.run", return_value=_completed(stdout="30, 2048, 8192, Test GPU\n")
        ):
            sample = gpu_stats.read_gpus()
        self.assertTrue(sample["ok"])
        self.assertEqual(sample["gpus"][0]["memUsed"], 2048)

    def test_query_asks_for_the_fields_the_parser_expects(self):
        # The query string and the parser's field order are one contract split
        # across two places; a reordered query would parse into wrong keys.
        with mock.patch("shutil.which", return_value="/usr/bin/nvidia-smi"), mock.patch(
            "subprocess.run", return_value=_completed(stdout="1, 2, 3, X")
        ) as run:
            gpu_stats.read_gpus()
        argv = run.call_args.args[0]
        self.assertIn("--query-gpu=utilization.gpu,memory.used,memory.total,name", argv)
        self.assertIn("--format=csv,noheader,nounits", argv)


class FormatGpuStatusTests(unittest.TestCase):
    """format_gpu_status renders what the /gpu command prints."""

    def test_error_sample(self):
        text = gpu_stats.format_gpu_status({"ok": False, "error": "nvidia-smi not found on PATH"})
        self.assertEqual(text, "GPU Monitor: nvidia-smi not found on PATH")

    def test_error_sample_without_a_message(self):
        text = gpu_stats.format_gpu_status({"ok": False})
        self.assertEqual(text, "GPU Monitor: GPU statistics unavailable")

    def test_missing_ok_key_is_treated_as_failure(self):
        self.assertTrue(gpu_stats.format_gpu_status({}).startswith("GPU Monitor:"))

    def test_single_gpu_row(self):
        sample = {
            "ok": True,
            "gpus": [{"util": 42, "memUsed": 8192, "memTotal": 24564, "name": "RTX 4090"}],
        }
        self.assertEqual(
            gpu_stats.format_gpu_status(sample),
            "GPU 0 · 42% · VRAM 8.0/24.0 GiB · RTX 4090",
        )

    def test_multiple_gpus_are_indexed_and_newline_separated(self):
        sample = {
            "ok": True,
            "gpus": [
                {"util": 1, "memUsed": 1024, "memTotal": 2048, "name": "A"},
                {"util": 2, "memUsed": 1024, "memTotal": 2048, "name": "B"},
            ],
        }
        lines = gpu_stats.format_gpu_status(sample).splitlines()
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[0].startswith("GPU 0 "))
        self.assertTrue(lines[1].startswith("GPU 1 "))

    def test_ok_but_no_gpus(self):
        # ok=True with an empty list is reachable only from a caller building a
        # sample by hand, but the "".join of nothing would otherwise be blank.
        text = gpu_stats.format_gpu_status({"ok": True, "gpus": []})
        self.assertEqual(text, "GPU Monitor: no GPUs reported by nvidia-smi")


if __name__ == "__main__":
    unittest.main()
