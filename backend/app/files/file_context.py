import re

from app.files.local_files import LocalFileError, find_unique_readable_file, read_text_file


FILE_CONTEXT_PATTERNS = (
    r"(?:lis|lire|ouvre|analyse|resume|résume|resumer|résumer).{0,40}(?:fichier|file)\s+[`\"']?(?P<path>[^`\"'\n]+)",
    r"(?:resume|résume|analyse)\s+[`\"'](?P<path>[^`\"'\n]+)[`\"']",
)


def detect_file_context(message: str) -> dict[str, str] | None:
    for pattern in FILE_CONTEXT_PATTERNS:
        match = re.search(pattern, message, flags=re.IGNORECASE)
        if not match:
            continue

        path_hint = match.group("path").strip()
        path_hint = re.split(r"\s+(?:et|puis|stp|s'il|s’il)", path_hint, maxsplit=1)[0].strip()
        resolved = find_unique_readable_file(path_hint)
        if not resolved:
            raise LocalFileError(
                "Je n'ai pas trouve un fichier lisible unique pour cette demande. "
                "Utilise plutot le chemin exact ou l'endpoint /files/search."
            )

        root_name, relative_path = resolved
        file_payload = read_text_file(root_name, relative_path)

        return {
            "root": root_name,
            "path": relative_path,
            "content": str(file_payload["content"]),
        }

    return None
