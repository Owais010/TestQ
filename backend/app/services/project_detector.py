"""
Project Detector.

Inspects repository files to determine language, framework, package manager,
and execution commands. This is critical — TestQ must know WHAT it's dealing
with BEFORE trying to execute anything.

Supported V1 technologies:
- Next.js
- React (Vite / CRA)
- Node.js (generic)
- Python / FastAPI

Unsupported technologies are detected and rejected honestly.
"""

import json
import logging
import re
import os
from pathlib import Path

from app.schemas.common import ProjectConfig

logger = logging.getLogger("testq.detector")


class UnsupportedProjectError(Exception):
    """The project uses a technology not supported in V1."""

    def __init__(self, detected: str, message: str = ""):
        self.detected = detected
        super().__init__(message or f"Unsupported technology: {detected}")


class DetectionError(Exception):
    """Could not determine the project type."""

    pass


# Files that indicate unsupported technologies
UNSUPPORTED_INDICATORS = {
    "pom.xml": "Java / Maven",
    "build.gradle": "Java / Gradle",
    "build.gradle.kts": "Kotlin / Gradle",
    "Cargo.toml": "Rust",
    "go.mod": "Go",
    "Gemfile": "Ruby",
    "composer.json": "PHP",
    "Package.swift": "Swift",
    "*.csproj": "C# / .NET",
    "mix.exs": "Elixir",
    "pubspec.yaml": "Dart / Flutter",
}


def _read_json(path: Path) -> dict:
    """Safely read a JSON file."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        return {}


def _file_exists(repo_path: Path, *names: str) -> str | None:
    """Check if any of the named files exist and return the first match."""
    for name in names:
        if (repo_path / name).exists():
            return name
    return None


def _detect_package_manager(repo_path: Path) -> str:
    """Determine the Node.js package manager."""
    if (repo_path / "pnpm-lock.yaml").exists():
        return "pnpm"
    if (repo_path / "yarn.lock").exists():
        return "yarn"
    # Default to npm (package-lock.json or fallback)
    return "npm"


def _get_install_command(package_manager: str, has_lockfile: bool) -> str:
    """Get the install command for a package manager."""
    if package_manager == "pnpm":
        return "pnpm install --frozen-lockfile" if has_lockfile else "pnpm install"
    if package_manager == "yarn":
        return "yarn install --frozen-lockfile" if has_lockfile else "yarn install"
    # npm
    return "npm ci" if has_lockfile else "npm install"


def _detect_nextjs(repo_path: Path, pkg: dict) -> ProjectConfig | None:
    """Detect Next.js project."""
    deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}

    if "next" not in deps:
        return None

    # Check for next.config files
    has_next_config = _file_exists(
        repo_path,
        "next.config.js",
        "next.config.mjs",
        "next.config.ts",
    )

    # Even without config file, having 'next' in deps is enough
    pm = _detect_package_manager(repo_path)
    has_lockfile = _file_exists(
        repo_path, "package-lock.json", "yarn.lock", "pnpm-lock.yaml"
    )

    scripts = pkg.get("scripts", {})
    build_cmd = f"{pm} run build" if "build" in scripts else "npx next build"
    start_cmd = f"{pm} run start" if "start" in scripts else "npx next start"

    # Detect language
    has_ts = (repo_path / "tsconfig.json").exists()
    language = "typescript" if has_ts else "javascript"

    detected_files = ["package.json"]
    if has_next_config:
        detected_files.append(has_next_config)
    if has_ts:
        detected_files.append("tsconfig.json")

    return ProjectConfig(
        language=language,
        framework="nextjs",
        package_manager=pm,
        install_command=_get_install_command(pm, has_lockfile is not None),
        build_command=build_cmd,
        start_command=start_cmd,
        expected_port=3000,
        has_dockerfile=(repo_path / "Dockerfile").exists(),
        detected_files=detected_files,
    )


def _detect_vite_react(repo_path: Path, pkg: dict) -> ProjectConfig | None:
    """Detect React + Vite project."""
    deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}

    has_vite_config = _file_exists(
        repo_path, "vite.config.js", "vite.config.ts", "vite.config.mjs"
    )

    if "vite" not in deps and not has_vite_config:
        return None

    if "react" not in deps and "react-dom" not in deps:
        return None

    pm = _detect_package_manager(repo_path)
    has_lockfile = _file_exists(
        repo_path, "package-lock.json", "yarn.lock", "pnpm-lock.yaml"
    )
    scripts = pkg.get("scripts", {})

    build_cmd = f"{pm} run build" if "build" in scripts else "npx vite build"

    # Vite dev server for development — in sandbox we use preview or dev
    if "preview" in scripts:
        start_cmd = f"{pm} run preview -- --host 0.0.0.0"
    elif "start" in scripts:
        start_cmd = f"{pm} run start"
    else:
        start_cmd = f"npx vite preview --host 0.0.0.0"

    has_ts = (repo_path / "tsconfig.json").exists()

    detected_files = ["package.json"]
    if has_vite_config:
        detected_files.append(has_vite_config)

    return ProjectConfig(
        language="typescript" if has_ts else "javascript",
        framework="vite-react",
        package_manager=pm,
        install_command=_get_install_command(pm, has_lockfile is not None),
        build_command=build_cmd,
        start_command=start_cmd,
        expected_port=4173,  # Vite preview default
        has_dockerfile=(repo_path / "Dockerfile").exists(),
        detected_files=detected_files,
    )


def _detect_nodejs(repo_path: Path, pkg: dict) -> ProjectConfig | None:
    """Detect generic Node.js project (express, etc.)."""
    scripts = pkg.get("scripts", {})

    # Must have a start script
    if "start" not in scripts:
        return None

    pm = _detect_package_manager(repo_path)
    has_lockfile = _file_exists(
        repo_path, "package-lock.json", "yarn.lock", "pnpm-lock.yaml"
    )
    has_ts = (repo_path / "tsconfig.json").exists()

    build_cmd = f"{pm} run build" if "build" in scripts else None

    # Try to detect port from scripts or common patterns
    expected_port = 3000
    start_script = scripts.get("start", "")
    if "8080" in start_script:
        expected_port = 8080
    elif "8000" in start_script:
        expected_port = 8000
    elif "5000" in start_script:
        expected_port = 5000

    return ProjectConfig(
        language="typescript" if has_ts else "javascript",
        framework="nodejs",
        package_manager=pm,
        install_command=_get_install_command(pm, has_lockfile is not None),
        build_command=build_cmd,
        start_command=f"{pm} run start",
        expected_port=expected_port,
        has_dockerfile=(repo_path / "Dockerfile").exists(),
        detected_files=["package.json"],
    )


def _detect_fastapi(repo_path: Path) -> ProjectConfig | None:
    """Detect Python / FastAPI project."""
    # Check for Python project indicators
    has_requirements = (repo_path / "requirements.txt").exists()
    has_pyproject = (repo_path / "pyproject.toml").exists()

    if not has_requirements and not has_pyproject:
        return None

    # Look for FastAPI in dependencies
    fastapi_found = False

    if has_requirements:
        try:
            reqs = (repo_path / "requirements.txt").read_text(encoding="utf-8").lower()
            if "fastapi" in reqs:
                fastapi_found = True
        except (OSError, UnicodeDecodeError):
            pass

    if not fastapi_found and has_pyproject:
        try:
            pyproject = (repo_path / "pyproject.toml").read_text(encoding="utf-8").lower()
            if "fastapi" in pyproject:
                fastapi_found = True
        except (OSError, UnicodeDecodeError):
            pass

    if not fastapi_found:
        return None

    # Determine the main module
    # Common patterns: main.py, app/main.py, src/main.py, app.py
    main_module = "app.main:app"
    for candidate in [
        "app/main.py",
        "src/main.py",
        "main.py",
        "app.py",
        "server.py",
    ]:
        if (repo_path / candidate).exists():
            module_path = candidate.replace("/", ".").replace(".py", "")
            main_module = f"{module_path}:app"
            break

    install_cmd = "pip install -r requirements.txt" if has_requirements else "pip install ."

    detected_files = []
    if has_requirements:
        detected_files.append("requirements.txt")
    if has_pyproject:
        detected_files.append("pyproject.toml")

    return ProjectConfig(
        language="python",
        framework="fastapi",
        package_manager="pip",
        install_command=install_cmd,
        build_command=None,
        start_command=f"uvicorn {main_module} --host 0.0.0.0 --port 8000",
        expected_port=8000,
        has_dockerfile=(repo_path / "Dockerfile").exists(),
        detected_files=detected_files,
    )


def _check_unsupported(repo_path: Path) -> str | None:
    """Check for files that indicate an unsupported technology."""
    for filename, tech in UNSUPPORTED_INDICATORS.items():
        if filename.startswith("*"):
            # Glob pattern
            ext = filename[1:]  # e.g., ".csproj"
            if any(repo_path.glob(f"*{ext}")) or any(repo_path.glob(f"**/*{ext}")):
                return tech
        elif (repo_path / filename).exists():
            return tech
    return None


def _detect_root(repo_path: str | Path) -> ProjectConfig:
    """
    Detect the project type from repository files.

    Order of detection (most specific first):
    1. Check for unsupported technologies → reject honestly
    2. Next.js
    3. React + Vite
    4. Generic Node.js
    5. FastAPI

    Args:
        repo_path: Path to the cloned repository.

    Returns:
        ProjectConfig with normalized execution configuration.

    Raises:
        UnsupportedProjectError: If technology is detected but not supported.
        DetectionError: If project type cannot be determined.
    """
    repo_path = Path(repo_path)

    if not repo_path.exists():
        raise DetectionError(f"Repository path does not exist: {repo_path}")

    # Check for unsupported technologies first
    unsupported = _check_unsupported(repo_path)
    if unsupported:
        raise UnsupportedProjectError(
            unsupported,
            f"Detected technology: {unsupported}. "
            "Not supported in TestQ V1. "
            "Supported: Next.js, React/Vite, Node.js, Python/FastAPI.",
        )

    # Check for package.json (Node.js ecosystem)
    pkg_path = repo_path / "package.json"
    if pkg_path.exists():
        pkg = _read_json(pkg_path)
        if pkg:
            # Try detectors in order of specificity
            config = _detect_nextjs(repo_path, pkg)
            if config:
                logger.info(f"Detected: Next.js ({config.language})")
                return config

            config = _detect_vite_react(repo_path, pkg)
            if config:
                logger.info(f"Detected: React + Vite ({config.language})")
                return config

            config = _detect_nodejs(repo_path, pkg)
            if config:
                logger.info(f"Detected: Node.js ({config.language})")
                return config

    # Check for Python / FastAPI
    config = _detect_fastapi(repo_path)
    if config:
        logger.info("Detected: Python / FastAPI")
        return config

    # Nothing matched
    raise DetectionError(
        "Could not determine project type. "
        "No supported framework detected. "
        "TestQ V1 supports: Next.js, React/Vite, Node.js, Python/FastAPI. "
        "Ensure the repository has a package.json or requirements.txt."
    )


def _apply_port(config: ProjectConfig, path: Path, override=None) -> ProjectConfig:
    pkg = _read_json(path / "package.json")
    scripts = pkg.get("scripts", {})
    command = scripts.get("preview" if config.framework == "vite-react" and "preview" in scripts else "start", "")
    match = re.search(r"(?:\bPORT\s*=\s*|--port[=\s]+|-p\s+)(\d+)\b", command)
    port = int(match.group(1)) if match else None
    if port is None and config.framework == "nodejs":
        for name in ("server.js", "index.js", "app.js", "server.ts", "src/index.ts"):
            file = path / name
            if file.is_file() and file.stat().st_size < 1024 * 1024:
                source = file.read_text(encoding="utf-8", errors="replace")
                match = re.search(r"(?:\.listen\(\s*|\bPORT\s*\|\|\s*|\bport\s*=\s*)(\d+)\b", source)
                if match:
                    port = int(match.group(1))
                    break
    port = override if override is not None else port
    if port is not None:
        if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
            raise DetectionError("Invalid application port")
        config.expected_port = port
    if config.framework == "vite-react":
        # Force the selected port; Vite must not silently choose a different one.
        config.start_command += f" --port {config.expected_port} --strictPort"
    if config.framework == "fastapi":
        config.start_command = re.sub(r"--port \d+", f"--port {config.expected_port}", config.start_command)
    return config


def detect_project(repo_path: str | Path) -> ProjectConfig:
    """Root first, then one unambiguous app within two directory levels.

    testq.json can select {"project_dir": "apps/web", "port": 4567}.
    Shared-workspace dependency orchestration is deliberately out of scope.
    """
    root = Path(repo_path).resolve()
    if not root.is_dir():
        raise DetectionError(f"Repository path does not exist: {root}")
    metadata = _read_json(root / "testq.json")
    selected = metadata.get("project_dir")
    if selected is not None:
        if not isinstance(selected, str):
            raise DetectionError("project_dir must be a relative directory")
        target = (root / selected).resolve()
        if not target.is_relative_to(root):
            raise DetectionError("project_dir escapes repository")
        config = _apply_port(_detect_root(target), target, metadata.get("port"))
        config.project_dir = target.relative_to(root).as_posix()
        return config
    try:
        return _apply_port(_detect_root(root), root, metadata.get("port"))
    except UnsupportedProjectError:
        raise
    except DetectionError:
        pass
    candidates = []
    visited = 0
    for directory, dirs, files in os.walk(root, followlinks=False):
        path = Path(directory)
        depth = len(path.relative_to(root).parts)
        dirs[:] = sorted(d for d in dirs if d not in {
            ".git", "node_modules", ".venv", "venv", "__pycache__"
        } and not d.startswith(".") and not (path / d).is_symlink()) if depth < 2 else []
        visited += 1
        if visited > 100:
            raise DetectionError("Too many application directories; select project_dir in testq.json")
        if depth == 0 or not {"package.json", "requirements.txt", "pyproject.toml"}.intersection(files):
            continue
        try:
            config = _apply_port(_detect_root(path), path, metadata.get("port"))
            config.project_dir = path.relative_to(root).as_posix()
            candidates.append(config)
        except (DetectionError, UnsupportedProjectError):
            continue
    if len(candidates) == 1:
        return candidates[0]
    if candidates:
        raise DetectionError("Ambiguous nested apps; select project_dir in testq.json: " +
                             ", ".join(c.project_dir for c in candidates))
    raise DetectionError("No supported application detected")
