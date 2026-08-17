import re
import shutil
from datetime import datetime
from pathlib import Path

from ...config import ToolkitConfig
from ...utils import FileUtils, get_logger

logger = get_logger(__name__)


class FileEditLocal:
    def __init__(self, config: ToolkitConfig = None) -> None:
        self.default_encoding = config.config.get("default_encoding", "utf-8")
        self.backup_enabled = config.config.get("backup_enabled", False)
        self.setup_workspace(config.config.get("workspace_root", "/tmp/"))
        logger.info(
            f"FileEditToolkit initialized with output directory: {self.work_dir}, encoding: {self.default_encoding}"
        )

    def setup_workspace(self, workspace_root: str):
        self.work_dir = Path(workspace_root).resolve()
        self.work_dir.mkdir(parents=True, exist_ok=True)

    def _sanitize_filename(self, filename: str) -> str:
        safe = re.sub(r"[^\w\-.]", "_", filename)
        return safe

    def _resolve_filepath(self, file_path: str) -> Path:
        path_obj = Path(file_path)
        if not path_obj.is_absolute():
            path_obj = self.work_dir / path_obj

        sanitized_filename = self._sanitize_filename(path_obj.name)
        path_obj = path_obj.parent / sanitized_filename
        resolved_path = path_obj.resolve()

        # Security check: ensure the resolved path is within work_dir
        try:
            resolved_path.relative_to(self.work_dir)
        except ValueError:
            raise ValueError(f"Path {resolved_path} is outside the allowed workspace {self.work_dir}")

        self._create_backup(resolved_path)
        return resolved_path

    def _create_backup(self, file_path: Path) -> None:
        if not self.backup_enabled or not file_path.exists():
            return
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = file_path.parent / f"{file_path.name}.{timestamp}.bak"
        shutil.copy2(file_path, backup_path)
        logger.info(f"Created backup at {backup_path}")

    async def read_file(self, path: str) -> str:
        path_obj = self._resolve_filepath(path)
        return path_obj.read_text()

    async def write_file(self, path: str, file_text: str) -> str:
        path_obj = self._resolve_filepath(path)
        path_obj.parent.mkdir(parents=True, exist_ok=True)
        path_obj.write_text(file_text)
        return f"Successfully wrote file: {path_obj}"

    async def edit_file(self, path: str, diff: str) -> str:
        resolved_path = self._resolve_filepath(path)

        with open(resolved_path, encoding=self.default_encoding) as f:
            content = f.read()
        try:
            modified_content = FileUtils.apply_diff(content, diff)
            with open(resolved_path, "w", encoding=self.default_encoding) as f:
                f.write(modified_content)
            return f"Successfully edited file: {resolved_path}"
        except ValueError as ve:
            logger.error(f"Error applying diff to file {resolved_path}: {ve}")
            return f"Error editing file: {ve}"
