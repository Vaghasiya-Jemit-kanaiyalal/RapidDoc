"""Connect working brain models into backend/models.

Downloads:
  1. rapiddoc_intent_model  <- typeform/distilbert-base-uncased-mnli (zero-shot NLI)
  2. rapiddoc_text_rewriter <- grammarly/coedit-small (CoEdIT T5, "rewrite:" style)

Both are pulled with huggingface_hub into the exact dirs the backend config
points at. Any failure raises a clear error (script is run manually).
"""
import os
import sys
import shutil
import tempfile

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.path.join(BACKEND_DIR, "models")
INTENT_TARGET = os.path.join(MODELS_DIR, "rapiddoc_intent_model")
REWRITER_TARGET = os.path.join(MODELS_DIR, "rapiddoc_text_rewriter")

INTENT_REPO = "typeform/distilbert-base-uncased-mnli"
REWRITER_REPO = "jbochi/coedit-small"


def download(repo_id: str, target: str) -> None:
    from huggingface_hub import snapshot_download

    os.makedirs(target, exist_ok=True)
    print(f"[1/2] Downloading {repo_id} ...")
    tmp = tempfile.mkdtemp(prefix="rapiddoc_model_")
    try:
        snapshot_download(repo_id=repo_id, local_dir=tmp, local_dir_use_symlinks=False)
        files = [f for f in os.listdir(tmp) if f not in (".", "..")]
        for f in files:
            src = os.path.join(tmp, f)
            dst = os.path.join(target, f)
            if os.path.isdir(src):
                if os.path.exists(dst):
                    shutil.rmtree(dst)
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)
        count = len(os.listdir(target))
        print(f"    OK -> {target} ({count} files)")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> None:
    if not (sys.version_info >= (3, 8)):
        raise SystemExit("Python 3.8+ required.")
    intended_repos = [INTENT_REPO, REWRITER_REPO]
    targets = [INTENT_TARGET, REWRITER_TARGET]
    for repo, tgt in zip(intended_repos, targets):
        try:
            download(repo, tgt)
        except Exception as exc:
            raise SystemExit(f"Failed to download {repo}: {exc}")


if __name__ == "__main__":
    main()