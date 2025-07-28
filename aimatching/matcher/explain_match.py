from .embedding_utils import get_embedding
import numpy as np
from .data_extractors import (
    get_teaching_text,
    get_experience_text,
    get_credentials_text,
    get_preference_text,
)
import subprocess
import re
from django.conf import settings

def generate_mistral_explanation(prompt: str) -> str:
    try:
        llama_cpp_path = settings.BASE_DIR / "aimatching" / "models" / "llama-run.exe"
        mistral_model_path = settings.BASE_DIR / "aimatching" / "models" / "mistral-7b-instruct-v0.1.Q6_K.gguf"

        result = subprocess.run(
            [
                str(llama_cpp_path),
                str(mistral_model_path),
                prompt
            ],
            capture_output=True,
            text=True,
            check=True
        )

        cleaned_output = re.sub(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])', '', result.stdout)
        return cleaned_output.strip()
    except subprocess.CalledProcessError as e:
        return f"⚠️ Mistral error: {e.stderr.strip()}"
    except Exception as e:
        return f"⚠️ Unexpected error: {str(e)}"