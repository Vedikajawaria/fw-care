from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1] / "frontend" / "src"
EMOJI = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF]",
)
CSS_RADIUS = re.compile(r"border-radius\s*:\s*([^;]+)", re.IGNORECASE)


def main() -> int:
    errors = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix not in {".ts", ".tsx", ".css"}:
            continue
        text = path.read_text(encoding="utf-8")
        checks = [
            ("em dash", "—" in text),
            ("emoji", bool(EMOJI.search(text))),
        ]
        if path.suffix == ".css":
            rounded_corners = any(
                float(match.group(1).strip().removesuffix("px").strip()) > 2
                for match in CSS_RADIUS.finditer(text)
            )
            checks.extend(
                [
                    ("gradient", "gradient(" in text.lower()),
                    ("rounded corners", rounded_corners),
                ]
            )
        for label, failed in checks:
            if failed:
                errors.append(f"{path.relative_to(ROOT)}: banned {label}")
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print("UI rules passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
