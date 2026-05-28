"""
Test runner — detects what test framework a project uses and runs it.
Returns True if all tests pass, False otherwise.
"""
import os
import subprocess
from pathlib import Path
from dataclasses import dataclass


@dataclass
class TestResult:
    passed: bool
    framework: str
    output: str
    returncode: int


def detect_framework(project_path: str) -> str | None:
    """Detect what test framework the project uses."""
    p = Path(project_path)

    # Flutter/Dart
    if (p / "pubspec.yaml").exists():
        return "flutter"

    # Python
    if (p / "pytest.ini").exists() or (p / "setup.cfg").exists() or (p / "pyproject.toml").exists():
        return "pytest"
    if list(p.rglob("test_*.py")) or list(p.rglob("*_test.py")):
        return "pytest"

    # Node / JS / TS
    pkg = p / "package.json"
    if pkg.exists():
        try:
            import json
            data = json.loads(pkg.read_text())
            scripts = data.get("scripts", {})
            test_script = scripts.get("test", "")
            if "jest" in test_script or (p / "jest.config.js").exists() or (p / "jest.config.ts").exists():
                return "jest"
            if "vitest" in test_script:
                return "vitest"
            if "mocha" in test_script:
                return "mocha"
            if test_script:
                return "npm_test"
        except Exception:
            pass
        return "npm_test"

    # Go
    if list(p.rglob("*_test.go")):
        return "go_test"

    # Java / Kotlin — Gradle
    if (p / "build.gradle").exists() or (p / "build.gradle.kts").exists():
        return "gradle"

    # Ruby
    if (p / "Gemfile").exists():
        return "rspec"

    # Rust
    if (p / "Cargo.toml").exists():
        return "cargo_test"

    return None


def run_tests(project_path: str, framework: str | None = None, timeout: int = 300) -> TestResult:
    """Run the test suite and return results."""
    if framework is None:
        framework = detect_framework(project_path)

    if framework is None:
        return TestResult(
            passed=True,
            framework="none",
            output="No test framework detected — skipping tests.",
            returncode=0,
        )

    commands = {
        "flutter":   ["flutter", "test", "--no-pub"],
        "pytest":    ["python3", "-m", "pytest", "--tb=short", "-q"],
        "jest":      ["npx", "jest", "--passWithNoTests"],
        "vitest":    ["npx", "vitest", "run"],
        "mocha":     ["npx", "mocha"],
        "npm_test":  ["npm", "test", "--", "--passWithNoTests"],
        "go_test":   ["go", "test", "./..."],
        "gradle":    ["./gradlew", "test"],
        "rspec":     ["bundle", "exec", "rspec"],
        "cargo_test":["cargo", "test"],
    }

    cmd = commands.get(framework)
    if cmd is None:
        return TestResult(passed=True, framework=framework, output="Unknown framework.", returncode=0)

    try:
        result = subprocess.run(
            cmd,
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = (result.stdout + result.stderr).strip()
        return TestResult(
            passed=result.returncode == 0,
            framework=framework,
            output=output[-3000:] if len(output) > 3000 else output,
            returncode=result.returncode,
        )
    except subprocess.TimeoutExpired:
        return TestResult(
            passed=False,
            framework=framework,
            output=f"Tests timed out after {timeout}s.",
            returncode=-1,
        )
    except FileNotFoundError:
        return TestResult(
            passed=False,
            framework=framework,
            output=f"Could not run '{cmd[0]}' — is it installed?",
            returncode=-1,
        )
    except Exception as e:
        return TestResult(passed=False, framework=framework, output=str(e), returncode=-1)
