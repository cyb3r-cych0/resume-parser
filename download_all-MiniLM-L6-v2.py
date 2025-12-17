import shutil
from pathlib import Path
from sentence_transformers import SentenceTransformer

# Constants
MODEL_NAME = "all-MiniLM-L6-v2"
BASE_DIR = Path(__file__).resolve().parent
# Change folder name slightly to avoid conflict if necessary,
# or ensure it's not created before the download
MODEL_PATH = BASE_DIR / "models" / MODEL_NAME


def get_model(retries=1):
    try:
        # Check for critical file to verify basic structure
        if not (MODEL_PATH / "modules.json").exists():
            raise FileNotFoundError("Local model files are missing.")

        print(f"Loading local model from {MODEL_PATH}...")
        return SentenceTransformer(str(MODEL_PATH))

    except (ValueError, FileNotFoundError, Exception) as e:
        if retries > 0:
            print(f"Local model error: {e}. Re-downloading...")

            if MODEL_PATH.exists():
                shutil.rmtree(MODEL_PATH)

            # FIX: Download from Hub FIRST, then save to the path
            model = SentenceTransformer(MODEL_NAME)  # This downloads to cache
            MODEL_PATH.mkdir(parents=True, exist_ok=True)
            model.save(str(MODEL_PATH))  # This saves to your local folder
            print(f"Download Successful.\nLoading local model from {MODEL_PATH}...")

            return model
        else:
            raise


if __name__ == "__main__":
    model = get_model()
