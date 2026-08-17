"""F3: o gate de ambiente falha com diagnóstico acionável quando o Python/PyInstaller divergem do aprovado."""
import collections
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import release  # noqa: E402

_VersionInfo = collections.namedtuple("VersionInfo", "major minor micro releaselevel serial")


class _FakePyInstaller:
    __version__ = "6.0.0"


class BuildEnvironmentGateTest(unittest.TestCase):
    def _run_with(self, version_tuple, pyinstaller_version):
        original_info = sys.version_info
        original_module = sys.modules.get("PyInstaller")
        try:
            sys.version_info = _VersionInfo(*version_tuple, "", 0)  # type: ignore[assignment]
            if pyinstaller_version is None:
                sys.modules.pop("PyInstaller", None)
            else:
                fake = _FakePyInstaller()
                fake.__version__ = pyinstaller_version
                sys.modules["PyInstaller"] = fake
            try:
                release.verify_build_environment()
                return None
            except release.ValidationError as exc:
                return str(exc)
        finally:
            sys.version_info = original_info
            if original_module is not None:
                sys.modules["PyInstaller"] = original_module
            else:
                sys.modules.pop("PyInstaller", None)

    def test_approved_environment_passes(self):
        self.assertIsNone(self._run_with((3, 11, 0), "6.21.0"))

    def test_divergent_python_fails_with_diagnostic(self):
        message = self._run_with((3, 11, 15), "6.21.0")
        self.assertIsNotNone(message)
        self.assertIn("Python", message)
        self.assertIn("3.11.0", message)

    def test_divergent_pyinstaller_fails_with_diagnostic(self):
        message = self._run_with((3, 11, 0), "6.0.0")
        self.assertIsNotNone(message)
        self.assertIn("PyInstaller", message)
        self.assertIn("6.21.0", message)

    def test_missing_pyinstaller_fails_with_diagnostic(self):
        import builtins

        original_import = builtins.__import__
        original_module = sys.modules.get("PyInstaller")
        sys.modules.pop("PyInstaller", None)

        def fake_import(name, *args, **kwargs):
            if name == "PyInstaller":
                raise ImportError("simulado")
            return original_import(name, *args, **kwargs)

        builtins.__import__ = fake_import
        try:
            info = _VersionInfo(3, 11, 0, "", 0)
            original_info = sys.version_info
            sys.version_info = info  # type: ignore[assignment]
            try:
                with self.assertRaises(release.ValidationError) as ctx:
                    release.verify_build_environment()
            finally:
                sys.version_info = original_info
        finally:
            builtins.__import__ = original_import
            if original_module is not None:
                sys.modules["PyInstaller"] = original_module
        self.assertIn("não instalado", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
