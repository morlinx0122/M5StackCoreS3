import argparse
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Download CosyVoice models via ModelScope.")
    parser.add_argument(
        "--model",
        default="iic/CosyVoice2-0.5B",
        help="ModelScope model id, e.g. iic/CosyVoice2-0.5B",
    )
    parser.add_argument(
        "--output",
        default=".models",
        help="Local directory for downloaded model snapshots.",
    )
    args = parser.parse_args()

    try:
        from modelscope import snapshot_download
    except ImportError as exc:
        raise SystemExit(
            "modelscope is not installed. Run: .\\.venv\\Scripts\\python.exe -m pip install modelscope"
        ) from exc

    output_dir = Path(args.output).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    path = snapshot_download(args.model, local_dir=str(output_dir / args.model.rsplit("/", 1)[-1]))
    print(path)


if __name__ == "__main__":
    main()
