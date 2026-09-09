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
import sys
import tempfile
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

    def test_na_utilization_keeps_the_gpu_with_its_vram(self):
        # nvidia-smi reports [N/A] for utilization.gpu on MIG-enabled and some
        # virtualized cards. The VRAM figures beside it are real, so the GPU
        # must survive rather than vanish from the chip and /gpu.
        sample = gpu_stats._parse_output("[N/A], 1024, 8192, NVIDIA A100-SXM4-40GB")
        self.assertTrue(sample["ok"])
        self.assertEqual(len(sample["gpus"]), 1)
        gpu = sample["gpus"][0]
        self.assertIsNone(gpu["util"])
        self.assertEqual(gpu["memUsed"], 1024)
        self.assertEqual(gpu["memTotal"], 8192)
        self.assertEqual(gpu["name"], "NVIDIA A100-SXM4-40GB")

    def test_na_memory_still_skips_the_row(self):
        # VRAM is what makes a row worth keeping; without it there is nothing
        # to show.
        sample = gpu_stats._parse_output("42, [N/A], [N/A], Broken GPU\n7, 100, 200, Good GPU")
        self.assertEqual(len(sample["gpus"]), 1)
        self.assertEqual(sample["gpus"][0]["name"], "Good GPU")

    def test_zero_total_memory_skips_the_row(self):
        # A zero memory.total is a driver or vGPU glitch, not a card. Every
        # consumer divides by it - the chip's VRAM warning and /gpu's GiB
        # figures both - so the row is dropped here rather than guarded once
        # per reader.
        sample = gpu_stats._parse_output("42, 0, 0, Glitched GPU\n7, 100, 200, Good GPU")
        self.assertEqual(len(sample["gpus"]), 1)
        self.assertEqual(sample["gpus"][0]["name"], "Good GPU")

    def test_only_a_zero_total_row_is_an_error(self):
        sample = gpu_stats._parse_output("42, 0, 0, Glitched GPU")
        self.assertFalse(sample["ok"])
        self.assertIn("unparseable nvidia-smi output", sample["error"])

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

    def test_missing_nvidia_smi_on_a_machine_that_has_a_card(self):
        # Patched rather than left to the host: this suite runs on CI machines
        # with no NVIDIA hardware, where the unpatched call would take the
        # quiet no-GPU path below and this assertion would be meaningless.
        with mock.patch("shutil.which", return_value=None), mock.patch.object(
            gpu_stats, "has_nvidia_hardware", return_value=True
        ):
            sample = gpu_stats.read_gpus()
        self.assertEqual(sample, {"ok": False, "error": "nvidia-smi not found on PATH"})

    def test_missing_nvidia_smi_when_hardware_presence_is_unknown(self):
        # Unknown is not absence. Assuming absence would silently hide a real
        # driver problem on any platform the detection does not cover.
        with mock.patch("shutil.which", return_value=None), mock.patch.object(
            gpu_stats, "has_nvidia_hardware", return_value=None
        ):
            sample = gpu_stats.read_gpus()
        self.assertEqual(sample, {"ok": False, "error": "nvidia-smi not found on PATH"})
        self.assertNotIn("reason", sample)

    def test_no_nvidia_hardware_is_quiet_not_an_error(self):
        with mock.patch("shutil.which", return_value=None), mock.patch.object(
            gpu_stats, "has_nvidia_hardware", return_value=False
        ):
            sample = gpu_stats.read_gpus()
        self.assertEqual(
            sample,
            {
                "ok": False,
                "reason": gpu_stats.NO_GPU,
                "error": "no NVIDIA GPU detected on this machine",
            },
        )

    def test_only_the_no_gpu_result_carries_a_reason(self):
        # The desktop chip keys off `reason` alone, so a driver failure must
        # never grow one - it would hide the chip on a machine with a real
        # problem.
        with mock.patch("shutil.which", return_value="/usr/bin/nvidia-smi"), mock.patch(
            "subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="nvidia-smi", timeout=5)
        ):
            self.assertNotIn("reason", gpu_stats.read_gpus())

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

    def test_na_utilization_renders_as_unavailable(self):
        text = gpu_stats.format_gpu_status(
            {"ok": True, "gpus": [
                {"util": None, "memUsed": 1024, "memTotal": 8192, "name": "A100"}
            ]}
        )
        self.assertIn("util n/a", text)
        self.assertIn("VRAM 1.0/8.0 GiB", text)
        self.assertNotIn("None", text)

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

    def test_no_gpu_reads_as_a_statement_of_fact(self):
        text = gpu_stats.format_gpu_status(
            {
                "ok": False,
                "reason": gpu_stats.NO_GPU,
                "error": "no NVIDIA GPU detected on this machine",
            }
        )
        self.assertEqual(text, "GPU Monitor: no NVIDIA GPU detected on this machine")
        self.assertEqual(len(text.splitlines()), 1)


class HardwareDetectionTests(unittest.TestCase):
    """has_nvidia_hardware() answers "is a card installed", not "does it work"."""

    def setUp(self):
        # The answer is cached for the process, so every test starts clean.
        self.reset_cache()
        self.addCleanup(self.reset_cache)

    @staticmethod
    def reset_cache():
        setattr(gpu_stats, "_hardware_checked", False)
        setattr(gpu_stats, "_hardware_answer", None)

    def make_sysfs(self, *vendors):
        """A stand-in for /sys/bus/pci/devices holding one entry per vendor id.

        Real entries are named like `0000:01:00.0`; these are not, because a
        colon cannot appear in a Windows filename and the suite runs here. The
        code iterates the directory and never parses the names, so the
        substitution changes nothing it depends on.
        """
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        root = Path(holder.name)
        for index, vendor in enumerate(vendors):
            device = root / f"device-{index}"
            device.mkdir()
            if vendor is not None:
                (device / "vendor").write_text(vendor, encoding="ascii")
        return root

    def linux_answer(self, root):
        with mock.patch.object(gpu_stats, "_PCI_DEVICES", root):
            return gpu_stats._linux_has_nvidia()

    def test_sysfs_reports_an_nvidia_vendor_id(self):
        self.assertIs(self.linux_answer(self.make_sysfs("0x8086\n", "0x10de\n")), True)

    def test_sysfs_with_devices_but_no_nvidia_is_a_real_no(self):
        self.assertIs(self.linux_answer(self.make_sysfs("0x8086\n", "0x1002\n")), False)

    def test_vendor_id_case_does_not_matter(self):
        self.assertIs(self.linux_answer(self.make_sysfs("0x10DE\n")), True)

    def test_a_device_with_no_readable_vendor_is_skipped(self):
        self.assertIs(self.linux_answer(self.make_sysfs(None, "0x10de\n")), True)

    def test_an_empty_sysfs_is_unknown_not_absence(self):
        # No vendor id read at all means sysfs is not populated the way this
        # check assumes, which is not evidence that the machine has no GPU.
        self.assertIsNone(self.linux_answer(self.make_sysfs()))
        self.assertIsNone(self.linux_answer(self.make_sysfs(None)))

    def test_a_missing_sysfs_is_unknown(self):
        self.assertIsNone(self.linux_answer(Path("no-such-directory-anywhere")))

    def test_macos_is_a_definitive_no(self):
        with mock.patch.object(sys, "platform", "darwin"):
            self.assertIs(gpu_stats.has_nvidia_hardware(), False)

    def test_an_unrecognised_platform_is_unknown(self):
        with mock.patch.object(sys, "platform", "sunos5"):
            self.assertIsNone(gpu_stats.has_nvidia_hardware())

    def test_the_answer_is_cached(self):
        with mock.patch.object(sys, "platform", "linux"), mock.patch.object(
            gpu_stats, "_linux_has_nvidia", return_value=False
        ) as probe:
            self.assertIs(gpu_stats.has_nvidia_hardware(), False)
            self.assertIs(gpu_stats.has_nvidia_hardware(), False)
        self.assertEqual(probe.call_count, 1)

    def test_an_unknown_answer_is_cached_too(self):
        with mock.patch.object(sys, "platform", "linux"), mock.patch.object(
            gpu_stats, "_linux_has_nvidia", return_value=None
        ) as probe:
            self.assertIsNone(gpu_stats.has_nvidia_hardware())
            self.assertIsNone(gpu_stats.has_nvidia_hardware())
        self.assertEqual(probe.call_count, 1)

    @unittest.skipUnless(sys.platform == "win32", "reads the Windows registry")
    def test_windows_registry_probe_answers_on_a_real_machine(self):
        # Not asserting which answer: the point is that the registry walk
        # completes and commits to a boolean rather than erroring out.
        self.assertIsInstance(gpu_stats._windows_has_nvidia(), bool)


if __name__ == "__main__":
    unittest.main()
